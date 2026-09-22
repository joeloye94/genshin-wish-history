# Backend

Python FastAPI app. Scope: this folder only — don't edit `../frontend`.

- Venv already set up in `venv/`; deps in `requirements.txt` (fastapi, uvicorn[standard])
- Run: `venv/Scripts/python.exe -m uvicorn main:app --reload --port 8000` (Windows) or `venv/bin/uvicorn main:app --reload --port 8000` (POSIX)
- Data: SQLite at `data/wishes.db` (see `db.py`); `fetcher.py` pulls wish history from a Genshin authkey URL via `POST /authkey`
- Layout: `main.py`/`db.py`/`fetcher.py`/`log_extractor.py` stay flat at the root (app small enough that a package nest would add import complexity for no gain); `tests/` has the test suite (run via `venv/Scripts/python.exe tests/test_scheduling.py`); `scripts/` has one-off/rerunnable maintenance tooling (`build_item_registry.py`, `import_paimon_backup.py`); `data/` has runtime/generated state (`wishes.db`, `paimon_item_data.json`), gitignored
- CORS is locked to `http://localhost:5173` / `127.0.0.1:5173` in `main.py` — update if the frontend's dev port changes
- `sync-flow.md` in this folder: technical diagram of the `/sync-now` + weekly-cron log-extraction flow. `workflow.png` is the general picture; read `sync-flow.md` before touching that code path.
