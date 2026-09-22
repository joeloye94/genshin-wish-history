"""One-time historical backfill: import wish history from a paimon.moe backup
JSON export into wishes.db, for pulls that predate this app's own API sync.

Usage: venv/Scripts/python.exe scripts/import_paimon_backup.py <path/to/backup.json>

Idempotent: each imported row's id is deterministic (f"paimon_{gacha_type}_{i}"),
and db.insert_pulls uses INSERT OR IGNORE, so rerunning is a safe no-op.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import db

ITEM_DATA_PATH = Path(__file__).parent.parent / "data" / "paimon_item_data.json"

# paimon.moe backup bucket -> this app's gacha_type. Deliberately keyed off
# the bucket, not each pull's own "code" field: the character-event bucket
# contains a real mix of code "301" and "400" (HoYoverse's two concurrent
# character-banner gacha_types), both of which paimon.moe treats as one
# "character event" history and which this app's frontend only ever filters
# as "301". fetcher.py also never syncs "400" (GACHA_TYPES has no 400 entry),
# so coercing 400 -> 301 here is required for these pulls to be visible in
# the UI at all, not just a cosmetic choice. ponytail: if the real sync ever
# starts tracking "400" as distinct, revisit this coercion.
BUCKET_TO_GACHA_TYPE = {
    "wish-counter-beginners": "100",
    "wish-counter-character-event": "301",
    "wish-counter-chronicled": "500",
    "wish-counter-standard": "200",
    "wish-counter-weapon-event": "302",
}


def _row_for_pull(pull: dict, gacha_type: str, index: int, uid: str, item_data: dict, fallback_log: list) -> dict:
    info = item_data.get(pull["id"])
    if info is None:
        fallback_log.append(pull["id"])
        name = pull["id"].replace("_", " ").replace("-", " ").title()
        item_type = "Character" if pull["type"] == "character" else "Weapon"
        rank_type = "3"  # flagged placeholder - not a real lookup, see report
    else:
        name = info["name"]
        item_type = info["type"]
        rank_type = str(info["rarity"])

    return {
        "id": f"paimon_{gacha_type}_{index}",
        "uid": uid,
        "gacha_type": gacha_type,
        "item_id": "",
        "count": "1",
        "time": pull["time"],
        "name": name,
        "lang": "en-us",
        "item_type": item_type,
        "rank_type": rank_type,
    }


def earliest_time_for_type(gacha_type: str) -> str | None:
    conn = db.get_conn()
    row = conn.execute(
        "SELECT MIN(time) AS mn FROM pulls WHERE gacha_type = ?", (gacha_type,)
    ).fetchone()
    conn.close()
    return row["mn"] if row else None


def main(backup_path: str):
    with open(backup_path, encoding="utf-8") as f:
        backup = json.load(f)
    with open(ITEM_DATA_PATH, encoding="utf-8") as f:
        item_data = json.load(f)

    uid = str(backup["wish-uid"])
    before_total = db.pull_count()
    print(f"Before: {before_total} total pulls in wishes.db")

    all_rows = []
    fallback_log = []
    report = []
    for bucket, gacha_type in BUCKET_TO_GACHA_TYPE.items():
        pulls = backup[bucket]["pulls"]
        boundary = earliest_time_for_type(gacha_type)
        if boundary is None:
            eligible = list(enumerate(pulls))
        else:
            eligible = [(i, p) for i, p in enumerate(pulls) if p["time"] < boundary]

        rows = [
            _row_for_pull(p, gacha_type, i, uid, item_data, fallback_log)
            for i, p in eligible
        ]
        all_rows.extend(rows)
        report.append((gacha_type, bucket, len(pulls), boundary, len(rows)))

    db.insert_pulls(all_rows)
    after_total = db.pull_count()

    print(f"{'gacha_type':<10}{'bucket':<28}{'backup_pulls':<14}{'db_boundary':<22}{'imported':<10}")
    for gacha_type, bucket, total, boundary, imported in report:
        print(f"{gacha_type:<10}{bucket:<28}{total:<14}{str(boundary):<22}{imported:<10}")

    print(f"\nAfter: {after_total} total pulls in wishes.db (+{after_total - before_total})")
    if fallback_log:
        print(f"\nWARNING: {len(fallback_log)} slugs had no item_data lookup, used title-cased fallback + placeholder rank_type '3': {fallback_log}")
    else:
        print("\nAll imported pulls resolved cleanly via paimon_item_data.json (no fallbacks used).")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("Usage: python scripts/import_paimon_backup.py <path/to/backup.json>")
    main(sys.argv[1])
