import json
import time
import urllib.parse
import urllib.request

import db

GACHA_TYPES = ["100", "200", "301", "302", "500"]
PAGE_SIZE = 20
REQUEST_DELAY_SECONDS = 0.3


class AuthkeyExpired(Exception):
    pass


# Real getGachaLog API endpoint for the overseas/global server (all of
# os_asia/os_euro/os_usa/os_cht share this one host - only the CN server
# uses a different domain, which this app doesn't target).
# Community docs (MadeBaruna/genshin-wish-url, sunfkny/genshin-gacha-export,
# jvergerolle/Genshin-Impact-Wish-history-API) all point to
# hk4e-api-os.hoyoverse.com, but that host is stale now - it CNAMEs to an
# unresponsive aliyunddos scrubbing domain and every request times out.
# Verified live against the real API on 2026-09-22 instead: this host+path
# returns {"retcode":-100,"message":"authkey error"} for a bad authkey (a
# real API response, not a 404/timeout).
GACHA_LOG_API_URL = "https://public-operation-hk4e-sg.hoyoverse.com/gacha_info/api/getGachaLog"


def parse_authkey_url(url: str):
    """Accepts either a real getGachaLog API url (manual-paste via /authkey -
    its own scheme://netloc/path IS the endpoint) or the wish-history webview
    PAGE url pulled from output_log.txt by log_extractor (its path is the
    game's webview page, not the API - reconstruct the known API url instead)."""
    parts = urllib.parse.urlsplit(url)
    params = dict(urllib.parse.parse_qsl(parts.query, keep_blank_values=True))
    if "authkey" not in params:
        raise ValueError("URL is missing an authkey parameter")
    params.pop("gacha_id", None)
    params.pop("init_type", None)

    if "getGachaLog" in parts.path:
        base_url = f"{parts.scheme}://{parts.netloc}{parts.path}"
    else:
        base_url = GACHA_LOG_API_URL
    return base_url, params


def _fetch_page(base_url: str, params: dict):
    query = urllib.parse.urlencode(params)
    req = urllib.request.Request(f"{base_url}?{query}", headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        payload = json.loads(resp.read().decode("utf-8"))

    if payload.get("retcode") != 0:
        msg = payload.get("message", "unknown error")
        if "authkey" in msg.lower() or payload.get("retcode") in (-100, 10001):
            raise AuthkeyExpired(msg)
        raise RuntimeError(f"API error: {msg} (retcode={payload.get('retcode')})")

    return payload.get("data", {}).get("list", [])


def _row(e: dict) -> dict:
    return {
        "id": e.get("id", ""),
        "uid": e.get("uid", ""),
        "gacha_type": e.get("gacha_type", ""),
        "item_id": e.get("item_id", ""),
        "count": e.get("count", "1"),
        "time": e.get("time", ""),
        "name": e.get("name", ""),
        "lang": e.get("lang", ""),
        "item_type": e.get("item_type", ""),
        "rank_type": e.get("rank_type", ""),
    }


def fetch_new_pulls(base_url: str, base_params: dict) -> int:
    """Walk each banner newest-first (end_id=0) and stop once we hit an id we
    already have. ponytail: assumes no gaps in stored history; a full re-sync
    (fetch_wish_history.py against a fresh authkey) is the fallback if that
    assumption is ever wrong."""
    total_new = 0
    for gacha_type in GACHA_TYPES:
        known_max = int(db.max_id_for_type(gacha_type))
        end_id = "0"
        page = 1
        while True:
            params = dict(base_params)
            params.update({
                "gacha_type": gacha_type,
                "size": str(PAGE_SIZE),
                "end_id": end_id,
                "page": str(page),
            })
            entries = _fetch_page(base_url, params)
            if not entries:
                break

            new_entries = [e for e in entries if int(e["id"]) > known_max]
            db.insert_pulls([_row(e) for e in new_entries])
            total_new += len(new_entries)

            if len(new_entries) < len(entries):
                break  # ran into already-known history, nothing older is new

            end_id = entries[-1]["id"]
            page += 1
            time.sleep(REQUEST_DELAY_SECONDS)

    return total_new
