# Frontend

React 19 + Vite app. Scope: this folder only — don't edit `../backend`.

- Dev server: `npm run dev` (default port 5173, Vite auto-bumps if taken)
- Lint: `npm run lint` (oxlint)
- Build: `npm run build`
- Talks to the FastAPI backend at `http://127.0.0.1:8000` (see `../backend/main.py` for CORS-allowed origins — update there if this app's dev port changes).
- The "Sync now" button hits `POST /sync-now`; see `../backend/docs/sync-flow.md` for the full technical flow (log extraction, error paths).
