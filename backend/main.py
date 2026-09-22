import asyncio
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

import db
import fetcher
import log_extractor

POLL_INTERVAL_SECONDS = int(os.environ.get("POLL_INTERVAL_SECONDS", 6 * 3600))
GMT8 = timezone(timedelta(hours=8))

# --- SSE broadcast: notify connected /events clients whenever a sync cycle
# finishes (success or failure). run_fetch_cycle() and its callers run on two
# different threads - sync route handlers (/authkey, /sync-now) execute in
# FastAPI's worker thread pool, while poll_loop()/weekly_log_sync_loop() run
# on the asyncio event loop thread. asyncio.Queue isn't thread-safe, so
# broadcast() always hops onto the loop via call_soon_threadsafe before
# touching any queue, regardless of which thread called it.
_subscribers: list[asyncio.Queue] = []
_loop: asyncio.AbstractEventLoop | None = None


def _put_on_loop(message: str) -> None:
    for q in _subscribers:
        q.put_nowait(message)


def broadcast(message: str = "refresh") -> None:
    """Notify all connected SSE clients. Safe to call from any thread."""
    if _loop is not None:
        _loop.call_soon_threadsafe(_put_on_loop, message)


def set_fetch_status(status: str, error: str | None) -> None:
    """db.update_fetch_status + broadcast, so every status change (ok, error,
    authkey_expired) pushes an SSE event to the frontend."""
    db.update_fetch_status(status, error)
    broadcast()


def run_fetch_cycle(base_url: str, params: dict) -> int:
    """Shared by the manual /authkey submit, the interval poller, and the
    weekly log-sync job: persist the (possibly new) authkey, fetch, and
    record status. Raises AuthkeyExpired if the key is dead."""
    db.save_config(base_url, params)
    try:
        new_count = fetcher.fetch_new_pulls(base_url, params)
        set_fetch_status("ok", None)
        return new_count
    except fetcher.AuthkeyExpired as e:
        set_fetch_status("authkey_expired", str(e))
        raise


async def poll_loop():
    while True:
        cfg = db.load_config()
        if cfg:
            try:
                run_fetch_cycle(cfg["base_url"], cfg["params"])
            except fetcher.AuthkeyExpired:
                pass
            except Exception as e:
                set_fetch_status("error", str(e))
        await asyncio.sleep(POLL_INTERVAL_SECONDS)


def next_monday_4am(now: datetime) -> datetime:
    """Next Monday 04:00 in `now`'s tz, strictly after `now`."""
    target = now.replace(hour=4, minute=0, second=0, microsecond=0)
    days_ahead = (0 - now.weekday()) % 7  # Monday == 0
    if days_ahead == 0 and now >= target:
        days_ahead = 7
    return target + timedelta(days=days_ahead)


async def weekly_log_sync_loop():
    """Re-extracts the authkey from the game's local webview log every Monday
    04:00 GMT+8, lined up with the weekly server reset. ponytail: only works
    if the game (and thus the webview log entry) has been opened recently
    enough that the extracted authkey hasn't already expired — same ceiling
    as any other use of this authkey, just automated."""
    while True:
        now = datetime.now(GMT8)
        target = next_monday_4am(now)
        await asyncio.sleep((target - now).total_seconds())

        url = log_extractor.extract_latest_url()
        if not url:
            set_fetch_status("error", "weekly log sync: no getGachaLog URL found in game log")
            continue
        try:
            base_url, params = fetcher.parse_authkey_url(url)
            run_fetch_cycle(base_url, params)
        except Exception as e:
            set_fetch_status("error", f"weekly log sync failed: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _loop
    db.init_db()
    _loop = asyncio.get_running_loop()
    tasks = [asyncio.create_task(poll_loop()), asyncio.create_task(weekly_log_sync_loop())]
    yield
    for t in tasks:
        t.cancel()


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class AuthkeyPayload(BaseModel):
    url: str


@app.post("/authkey")
def set_authkey(payload: AuthkeyPayload):
    try:
        base_url, params = fetcher.parse_authkey_url(payload.url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        new_count = run_fetch_cycle(base_url, params)
    except fetcher.AuthkeyExpired as e:
        raise HTTPException(status_code=400, detail=f"Authkey rejected: {e}")
    except Exception as e:
        set_fetch_status("error", str(e))
        raise HTTPException(status_code=502, detail=str(e))

    return {"new_pulls": new_count}


@app.post("/sync-now")
def sync_now():
    """Manual trigger for the same log-extract + fetch cycle the weekly job runs."""
    url = log_extractor.extract_latest_url()
    if not url:
        raise HTTPException(status_code=404, detail="No getGachaLog URL found in game log")

    try:
        base_url, params = fetcher.parse_authkey_url(url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        new_count = run_fetch_cycle(base_url, params)
    except fetcher.AuthkeyExpired as e:
        raise HTTPException(status_code=400, detail=f"Authkey rejected: {e}")
    except Exception as e:
        set_fetch_status("error", str(e))
        raise HTTPException(status_code=502, detail=str(e))

    return {"new_pulls": new_count}


@app.get("/status")
def get_status():
    cfg = db.load_config()
    return {
        "has_authkey": cfg is not None,
        "last_fetch_at": cfg["last_fetch_at"] if cfg else None,
        "last_status": cfg["last_status"] if cfg else None,
        "last_error": cfg["last_error"] if cfg else None,
        "total_pulls": db.pull_count(),
        "poll_interval_seconds": POLL_INTERVAL_SECONDS,
    }


@app.get("/pulls")
def list_pulls(gacha_type: str | None = None):
    return db.get_pulls(gacha_type)


@app.get("/events")
async def sse_events(request: Request):
    """SSE stream: pushes a 'refresh' message whenever a sync cycle finishes
    (success or failure), so the frontend can re-fetch /status + /pulls
    immediately instead of polling every 30s."""
    queue: asyncio.Queue = asyncio.Queue()
    _subscribers.append(queue)

    async def event_stream():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=15)
                    yield f"data: {message}\n\n"
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"  # SSE comment, keeps proxies from timing out the connection
        finally:
            _subscribers.remove(queue)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/export")
def export_pulls():
    """Full pulls table as a JSON array, for the user to download/back up.
    No gacha_type filter - frontend can filter client-side like the table does."""
    return db.get_pulls()
