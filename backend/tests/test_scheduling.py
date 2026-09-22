import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
import threading
from datetime import datetime, timedelta
from unittest.mock import patch

from fastapi import HTTPException

import db
import log_extractor
import main
from main import GMT8, next_monday_4am, sync_now


def test_next_monday_4am():
    cases = [
        # (now, expected_target)
        (datetime(2026, 9, 22, 10, 0, tzinfo=GMT8), datetime(2026, 9, 28, 4, 0, tzinfo=GMT8)),  # Tue -> next Mon
        (datetime(2026, 9, 28, 3, 59, tzinfo=GMT8), datetime(2026, 9, 28, 4, 0, tzinfo=GMT8)),  # Mon, just before 4am -> today
        (datetime(2026, 9, 28, 4, 0, tzinfo=GMT8), datetime(2026, 10, 5, 4, 0, tzinfo=GMT8)),  # Mon, exactly 4am -> next week
        (datetime(2026, 9, 28, 4, 1, tzinfo=GMT8), datetime(2026, 10, 5, 4, 0, tzinfo=GMT8)),  # Mon, just after 4am -> next week
        (datetime(2026, 9, 27, 23, 0, tzinfo=GMT8), datetime(2026, 9, 28, 4, 0, tzinfo=GMT8)),  # Sun night -> tomorrow
    ]
    for now, expected in cases:
        got = next_monday_4am(now)
        assert got == expected, f"now={now} -> got {got}, expected {expected}"
        assert got > now, f"target {got} must be strictly after now {now}"

    # invariant: whatever `now` is, the result is always a Monday at 04:00
    for offset_days in range(14):
        now = datetime(2026, 9, 21, 12, 0, tzinfo=GMT8) + timedelta(days=offset_days)
        target = next_monday_4am(now)
        assert target.weekday() == 0 and target.hour == 4 and target.minute == 0


def test_extract_latest_url(tmp_path):
    # The game logs the wish-history webview PAGE url, not a literal
    # getGachaLog url - regression fixture for that (see log_extractor.py).
    log = tmp_path / "output_log.txt"
    log.write_text(
        "some unrelated line\n"
        '[t] web: 1 url: https://sdk.hoyoverse.com/sw.html?bundle_id=hk4e_global&region=os_asia "trailing"\n'
        '[t] web: 2 url: https://gs.hoyoverse.com/genshin/event/e1/index.html?auth_appid=webview_gacha&authkey=OLD&gacha_id=1 "trailing"\n'
        "more noise\n"
        '[t] web: 2 url: https://gs.hoyoverse.com/genshin/event/e1/index.html?auth_appid=webview_gacha&authkey=NEW&gacha_id=2 "trailing"\n',
        encoding="utf-8",
    )
    url = log_extractor.extract_latest_url(str(log))
    assert url == "https://gs.hoyoverse.com/genshin/event/e1/index.html?auth_appid=webview_gacha&authkey=NEW&gacha_id=2"


def test_extract_latest_url_missing_file():
    assert log_extractor.extract_latest_url("/does/not/exist.txt") is None


# Sanitized (authkey truncated) real output_log.txt line, captured on this
# machine 2026-09-22. Regression test for the log_extractor regex + fetcher's
# API-url reconstruction actually matching/handling real game log output.
REAL_LOG_LINE = (
    "[2026-09-22 15:56:06.065] web: 2 url: "
    "https://gs.hoyoverse.com/genshin/event/e20190909gacha-df01aea2/index.html"
    "?win_mode=fullscreen&no_joypad_close=1&authkey_ver=1&sign_type=2"
    "&auth_appid=webview_gacha&init_type=200"
    "&gacha_id=0b8509e29bf33a648cbec07be1ef2240326e7cd2&timestamp=1786492187"
    "&lang=en&device_type=pc&game_version=OSRELWin7.0.0_R47805902_S47829085_D48215702"
    "&region=os_asia&authkey=ijIrnNSKb4y6CPxXqeD7REDACTED%3d%3d"
    '&game_biz=hk4e_global#/log,  enable_joypad_control :{"num":0,"type":0,"exchange":0}'
)


def test_extract_latest_url_real_log_line(tmp_path):
    log = tmp_path / "output_log.txt"
    log.write_text(REAL_LOG_LINE + "\n", encoding="utf-8")
    url = log_extractor.extract_latest_url(str(log))
    assert url is not None
    assert "authkey=ijIrnNSKb4y6CPxXqeD7REDACTED" in url
    assert "enable_joypad_control" not in url  # stops at the trailing comma, not mid-JSON

    import fetcher
    base_url, params = fetcher.parse_authkey_url(url)
    assert base_url == fetcher.GACHA_LOG_API_URL
    assert params["authkey"].startswith("ijIrnNSKb4y6CPxXqeD7")
    assert params["region"] == "os_asia"
    assert "gacha_id" not in params and "init_type" not in params


def test_paimon_backup_row_mapping():
    # Real sample pulls from the user's paimon.moe backup export, one
    # character and one weapon. Regression test for import_paimon_backup.py's
    # slug -> name/rarity/item_type translation and the code->gacha_type
    # bucket coercion (character-event bucket mixes real API codes "301" and
    # "400" - both must land on this app's "301" to be visible in the UI).
    from scripts import import_paimon_backup as backfill

    item_data = {
        "arlecchino": {"name": "Arlecchino", "rarity": 5, "type": "Character"},
        "wolfs_gravestone": {"name": "Wolf's Gravestone", "rarity": 5, "type": "Weapon"},
    }

    char_pull = {"type": "character", "code": "400", "id": "arlecchino", "time": "2024-05-01 12:00:00", "pity": 80}
    row = backfill._row_for_pull(char_pull, "301", 5, "853178098", item_data, [])
    assert row == {
        "id": "paimon_301_5",
        "uid": "853178098",
        "gacha_type": "301",
        "item_id": "",
        "count": "1",
        "time": "2024-05-01 12:00:00",
        "name": "Arlecchino",
        "lang": "en-us",
        "item_type": "Character",
        "rank_type": "5",
    }

    weap_pull = {"type": "weapon", "code": "302", "id": "wolfs_gravestone", "time": "2023-01-01 00:00:00", "pity": 1}
    row2 = backfill._row_for_pull(weap_pull, "302", 0, "853178098", item_data, [])
    assert row2["name"] == "Wolf's Gravestone"
    assert row2["item_type"] == "Weapon"
    assert row2["rank_type"] == "5"
    assert row2["id"] == "paimon_302_0"

    # unknown slug -> flagged fallback, not silently dropped
    fallback_log = []
    unknown_pull = {"type": "weapon", "code": "302", "id": "totally_unknown_slug", "time": "2023-01-01 00:00:00", "pity": 1}
    row3 = backfill._row_for_pull(unknown_pull, "302", 1, "853178098", {}, fallback_log)
    assert row3["name"] == "Totally Unknown Slug"
    assert row3["rank_type"] == "3"
    assert fallback_log == ["totally_unknown_slug"]


def test_resolve_icon_url():
    # Known-good character and weapon names resolve to the paimon.moe GitHub
    # raw-content icon URL for their slug; unknown/unresolvable names (e.g. a
    # very recently added item paimon.moe's data hasn't caught up to) -> None,
    # not a broken URL.
    assert db.resolve_icon_url("Character", "Arlecchino") == (
        "https://raw.githubusercontent.com/MadeBaruna/paimon-moe/main/static/images/characters/arlecchino.png"
    )
    assert db.resolve_icon_url("Weapon", "Wolf's Gravestone") == (
        "https://raw.githubusercontent.com/MadeBaruna/paimon-moe/main/static/images/weapons/wolfs_gravestone.png"
    )
    assert db.resolve_icon_url("Character", "Totally Unknown Character") is None
    assert db.resolve_icon_url("Weapon", "Arlecchino") is None  # wrong namespace


def test_broadcast_thread_safety():
    # /events subscribers must receive messages whether broadcast() is called
    # directly on the event loop (poll_loop/weekly_log_sync_loop's context)
    # or from a worker thread (the sync /authkey, /sync-now route handlers'
    # context, via FastAPI's threadpool) - regression test for the
    # call_soon_threadsafe hop in main.broadcast().
    async def run():
        main._loop = asyncio.get_running_loop()
        main._subscribers.clear()
        q = asyncio.Queue()
        main._subscribers.append(q)
        try:
            main.broadcast("from-loop")
            assert await asyncio.wait_for(q.get(), timeout=1) == "from-loop"

            t = threading.Thread(target=main.broadcast, args=("from-thread",))
            t.start()
            t.join()
            assert await asyncio.wait_for(q.get(), timeout=1) == "from-thread"
        finally:
            main._subscribers.remove(q)
            main._loop = None

    asyncio.run(run())


def test_broadcast_unsubscribe_no_leak():
    # A queue removed from _subscribers (client disconnect) must not receive
    # further messages, and broadcast() must not error over remaining ones.
    async def run():
        main._loop = asyncio.get_running_loop()
        main._subscribers.clear()
        q1, q2 = asyncio.Queue(), asyncio.Queue()
        main._subscribers.extend([q1, q2])
        main._subscribers.remove(q1)
        main.broadcast("x")
        await asyncio.sleep(0)  # let the call_soon_threadsafe callback run
        assert q1.empty()
        assert await asyncio.wait_for(q2.get(), timeout=1) == "x"
        main._subscribers.clear()
        main._loop = None

    asyncio.run(run())


def test_sync_now_malformed_url_is_400_not_500():
    # A getGachaLog URL missing `authkey` should 400 cleanly (matches /authkey),
    # not fall through to an unhandled 500. Regression test for main.py sync_now().
    with patch.object(
        log_extractor, "extract_latest_url",
        lambda: "https://example.com/getGachaLog?gacha_id=1",
    ):
        try:
            sync_now()
            assert False, "expected HTTPException"
        except HTTPException as e:
            assert e.status_code == 400, e.detail
            assert "authkey" in e.detail


if __name__ == "__main__":
    import tempfile
    from pathlib import Path

    test_next_monday_4am()
    with tempfile.TemporaryDirectory() as d:
        test_extract_latest_url(Path(d))
    with tempfile.TemporaryDirectory() as d:
        test_extract_latest_url_real_log_line(Path(d))
    test_extract_latest_url_missing_file()
    test_paimon_backup_row_mapping()
    test_resolve_icon_url()
    test_broadcast_thread_safety()
    test_broadcast_unsubscribe_no_leak()
    test_sync_now_malformed_url_is_400_not_500()
    print("all checks passed")
