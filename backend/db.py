import json
import re
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "wishes.db"
ITEM_DATA_PATH = Path(__file__).parent / "data" / "paimon_item_data.json"
BANNER_DATA_PATH = Path(__file__).parent / "data" / "banner_data.json"

ICON_BASE = "https://raw.githubusercontent.com/MadeBaruna/paimon-moe/main/static/images"
_ICON_TYPE_DIR = {"Character": "characters", "Weapon": "weapons"}

# Only these gacha_types have a rate-up/50-50 concept at all; Standard (200)
# and Beginner (100) pull from a single flat pool with no featured item, so
# won_fiftyfifty is always null for them (see resolve_won_fiftyfifty).
_FIFTYFIFTY_GACHA_TYPES = {"301", "302", "500"}


def _load_icon_index() -> dict:
    """(item_type, name) -> slug, inverted from the slug-keyed
    paimon_item_data.json (which import_paimon_backup.py also reads by slug -
    keep that file's shape as-is and index it here instead of duplicating it
    name-keyed on disk)."""
    with open(ITEM_DATA_PATH, encoding="utf-8") as f:
        item_data = json.load(f)
    return {(info["type"], info["name"]): slug for slug, info in item_data.items()}


_ICON_INDEX = _load_icon_index()


def _load_banner_data() -> dict:
    with open(BANNER_DATA_PATH, encoding="utf-8") as f:
        return json.load(f)


_BANNER_DATA = _load_banner_data()


def resolve_icon_url(item_type: str, name: str) -> str | None:
    slug = _ICON_INDEX.get((item_type, name))
    type_dir = _ICON_TYPE_DIR.get(item_type)
    if slug is None or type_dir is None:
        return None
    return f"{ICON_BASE}/{type_dir}/{slug}.png"


def resolve_won_fiftyfifty(gacha_type: str, item_type: str, name: str, time: str) -> bool | None:
    """Only meaningful for 5-star pulls on 301/302/500 (checked by the caller
    via rank_type) - null for 100/200 which have no rate-up concept. Looks up
    the banner phase active at `time` and checks whether the pulled item's
    slug is in that phase's featured list. For a 301 pull inside a dual-banner
    window (two concurrent character banners this app's import can't tell
    apart - see banner_data.json's "301_dual" and the comment in
    scripts/build_banner_data.py), the two phases' featured lists have
    already been unioned at build time, so the same "featured" lookup answers
    "did the rate-up land" without needing to know which specific banner."""
    if gacha_type not in _FIFTYFIFTY_GACHA_TYPES:
        return None
    slug = _ICON_INDEX.get((item_type, name))
    if slug is None:
        return None

    phases = _BANNER_DATA["301_dual"] if gacha_type == "301" else []
    phases = phases + _BANNER_DATA[gacha_type]
    for phase in phases:
        if phase["start"] <= time <= phase["end"]:
            return slug in phase["featured"]
    return None


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS pulls (
            id TEXT PRIMARY KEY,
            uid TEXT,
            gacha_type TEXT,
            item_id TEXT,
            count TEXT,
            time TEXT,
            name TEXT,
            lang TEXT,
            item_type TEXT,
            rank_type TEXT
        );
        CREATE TABLE IF NOT EXISTS config (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            base_url TEXT,
            params_json TEXT,
            last_fetch_at TEXT,
            last_status TEXT,
            last_error TEXT
        );
    """)
    conn.commit()
    conn.close()


def max_id_for_type(gacha_type: str) -> str:
    conn = get_conn()
    row = conn.execute(
        "SELECT MAX(CAST(id AS INTEGER)) AS m FROM pulls WHERE gacha_type = ?",
        (gacha_type,),
    ).fetchone()
    conn.close()
    return str(row["m"]) if row and row["m"] is not None else "0"


def insert_pulls(entries: list):
    if not entries:
        return
    conn = get_conn()
    conn.executemany(
        """INSERT OR IGNORE INTO pulls
           (id, uid, gacha_type, item_id, count, time, name, lang, item_type, rank_type)
           VALUES (:id, :uid, :gacha_type, :item_id, :count, :time, :name, :lang, :item_type, :rank_type)""",
        entries,
    )
    conn.commit()
    conn.close()


def save_config(base_url: str, params: dict):
    import json
    conn = get_conn()
    conn.execute(
        """INSERT INTO config (id, base_url, params_json, last_status, last_error)
           VALUES (1, ?, ?, 'pending', NULL)
           ON CONFLICT(id) DO UPDATE SET base_url = excluded.base_url,
                                          params_json = excluded.params_json,
                                          last_status = 'pending',
                                          last_error = NULL""",
        (base_url, json.dumps(params)),
    )
    conn.commit()
    conn.close()


def load_config():
    import json
    conn = get_conn()
    row = conn.execute("SELECT * FROM config WHERE id = 1").fetchone()
    conn.close()
    if not row:
        return None
    return {
        "base_url": row["base_url"],
        "params": json.loads(row["params_json"]),
        "last_fetch_at": row["last_fetch_at"],
        "last_status": row["last_status"],
        "last_error": row["last_error"],
    }


def update_fetch_status(status: str, error: str | None):
    conn = get_conn()
    conn.execute(
        "UPDATE config SET last_fetch_at = datetime('now'), last_status = ?, last_error = ? WHERE id = 1",
        (status, error),
    )
    conn.commit()
    conn.close()


def _chrono_sort_key(pull: dict):
    """`time` alone isn't a total order - multi-pulls (e.g. a 10-pull) share
    one identical timestamp, so same-timestamp rows need a tiebreaker that
    reflects real pull order, or pity counts can land on the wrong row within
    a batch. `id` breaks the tie, but the two id schemes in this table aren't
    comparable to each other: real API-synced ids are large numeric strings
    that increase monotonically with pull order (a well-documented property
    of Genshin's wish-history API, and confirmed against this app's own data:
    ids within one same-timestamp batch step by a constant offset), while
    historical paimon_<gacha_type>_<i> ids (import_paimon_backup.py) are a
    positional index assigned by enumerate() over the paimon.moe backup's
    pulls array - not numerically comparable to real ids, but consistent
    ascending order *within* that import. Since a paimon-imported row and a
    real-synced row never share an exact timestamp in practice (the backfill
    only imports pulls strictly before the earliest real-synced time per
    gacha_type), each id scheme only ever needs to be internally consistent,
    not cross-comparable - so this sorts numeric ids by value and falls back
    to the trailing integer of non-numeric ids, both ascending == chronological."""
    id_ = pull["id"]
    if id_.isdigit():
        return (pull["time"], int(id_))
    m = re.search(r"(\d+)$", id_)
    return (pull["time"], int(m.group(1)) if m else 0)


def _add_pity_and_fiftyfifty(pulls: list[dict]) -> None:
    by_gacha_type: dict[str, list[dict]] = {}
    for p in pulls:
        by_gacha_type.setdefault(p["gacha_type"], []).append(p)

    for gacha_type, group in by_gacha_type.items():
        ordered = sorted(group, key=_chrono_sort_key)
        pity = 0
        for p in ordered:
            pity += 1
            p["pity"] = pity
            if p["rank_type"] == "5":
                pity = 0
                p["won_fiftyfifty"] = resolve_won_fiftyfifty(gacha_type, p["item_type"], p["name"], p["time"])
            else:
                p["won_fiftyfifty"] = None


def get_pulls(gacha_type: str | None = None):
    conn = get_conn()
    if gacha_type:
        rows = conn.execute(
            "SELECT * FROM pulls WHERE gacha_type = ? ORDER BY time DESC", (gacha_type,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM pulls ORDER BY time DESC").fetchall()
    conn.close()
    pulls = [dict(r) for r in rows]
    for p in pulls:
        p["icon_url"] = resolve_icon_url(p["item_type"], p["name"])
    _add_pity_and_fiftyfifty(pulls)
    return pulls


def pull_count() -> int:
    conn = get_conn()
    row = conn.execute("SELECT COUNT(*) AS c FROM pulls").fetchone()
    conn.close()
    return row["c"]
