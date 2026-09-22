import json
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "wishes.db"
ITEM_DATA_PATH = Path(__file__).parent / "data" / "paimon_item_data.json"

ICON_BASE = "https://raw.githubusercontent.com/MadeBaruna/paimon-moe/main/static/images"
_ICON_TYPE_DIR = {"Character": "characters", "Weapon": "weapons"}


def _load_icon_index() -> dict:
    """(item_type, name) -> slug, inverted from the slug-keyed
    paimon_item_data.json (which import_paimon_backup.py also reads by slug -
    keep that file's shape as-is and index it here instead of duplicating it
    name-keyed on disk)."""
    with open(ITEM_DATA_PATH, encoding="utf-8") as f:
        item_data = json.load(f)
    return {(info["type"], info["name"]): slug for slug, info in item_data.items()}


_ICON_INDEX = _load_icon_index()


def resolve_icon_url(item_type: str, name: str) -> str | None:
    slug = _ICON_INDEX.get((item_type, name))
    type_dir = _ICON_TYPE_DIR.get(item_type)
    if slug is None or type_dir is None:
        return None
    return f"{ICON_BASE}/{type_dir}/{slug}.png"


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
    return pulls


def pull_count() -> int:
    conn = get_conn()
    row = conn.execute("SELECT COUNT(*) AS c FROM pulls").fetchone()
    conn.close()
    return row["c"]
