# Sync flow (technical)

For agents working on `/sync-now`, the weekly cron, or `log_extractor.py`/`fetcher.py`. See `workflow.png` for the general picture; this is the detail.

```mermaid
flowchart TD
    A["POST /sync-now\n(main.py)"] --> C
    B["weekly_log_sync_loop\nMonday 04:00 GMT+8\n(next_monday_4am)"] --> C

    C["log_extractor.extract_latest_url()\nreads %USERPROFILE%\\AppData\\LocalLow\\miHoYo\\Genshin Impact\\output_log.txt\nregex: last getGachaLog URL wins"]
    C -->|file missing or no match: None| C1
    C -->|url found| D

    C1["sync-now: 404 'No getGachaLog URL found in game log'\nweekly loop: update_fetch_status('error', ...), wait for next Monday"]

    D["fetcher.parse_authkey_url(url)\n-> base_url, params"]
    D -->|ValueError: no authkey param| D1
    D -->|ok| E

    D1["sync-now: 400 'Authkey rejected: ...' text\n(now caught like /authkey)\nweekly loop: caught by outer except -> status 'error'"]

    E["run_fetch_cycle(base_url, params)\nshared with /authkey, poll_loop, weekly loop"]
    E --> E1["db.save_config(): persist config, status='pending'"]
    E1 --> E2["fetcher.fetch_new_pulls(): call HoYoverse API,\ndedupe against db.max_id_for_type, insert new rows"]
    E2 -->|success| E3["db.update_fetch_status('ok', None)\nreturn new_count"]
    E2 -->|AuthkeyExpired| E4["db.update_fetch_status('authkey_expired', msg)\nre-raise"]

    E3 --> F["sync-now: 200 {new_pulls}\nweekly loop: done, wait for next Monday"]
    E4 --> F2["sync-now: 400 'Authkey rejected: ...'\nweekly loop: caught by outer except -> status 'error' (double status write)"]

    F --> G["Frontend: refresh() re-fetches /status + /pulls, updates table"]
```

## Known gap (fixed)

`sync_now()` previously didn't wrap `fetcher.parse_authkey_url()` in a try/except like `/authkey` does, so a malformed extracted URL (missing `authkey` param) would 500 instead of a clean 400. Fixed in `main.py`'s `sync_now()`: `ValueError` now maps to `HTTPException(400, ...)`, matching `/authkey`.
