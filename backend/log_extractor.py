import os
import re

DEFAULT_LOG_PATH = os.path.expandvars(
    r"%USERPROFILE%\AppData\LocalLow\miHoYo\Genshin Impact\output_log.txt"
)

# The game never logs a literal getGachaLog API call - it logs the wish
# history webview PAGE it opens (.../index.html?...&authkey=...). That page's
# query string carries the authkey; fetcher.parse_authkey_url() reconstructs
# the real API endpoint from it. `auth_appid=webview_gacha` uniquely tags
# this page among other `web: N url:` lines in output_log.txt (e.g.
# sdk.hoyoverse.com/sw.html), so it's what we match on.
# ponytail: matches up to the next whitespace/quote/comma; good enough for
# Chromium's plain-text net logging, not a general URL parser.
URL_RE = re.compile(r"https://[^\s\",]+auth_appid=webview_gacha[^\s\",]*")


def extract_latest_url(log_path: str | None = None) -> str | None:
    """Scan the game's webview log for the most recent wish-history webview
    page URL (last match wins, since the game keeps appending to this file
    across sessions)."""
    path = log_path or DEFAULT_LOG_PATH
    if not os.path.exists(path):
        return None

    latest = None
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            match = URL_RE.search(line)
            if match:
                latest = match.group(0)
    return latest
