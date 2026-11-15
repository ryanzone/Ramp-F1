# RAMP: Historical Replay and Time-Aware SQL Analytics

Summary of the upgrade. Nothing is committed to git.

## What was built

RAMP now replays a historical 2026 race on a virtual clock and answers questions about it with real SQL. Every answer only sees data up to the replay time. There is no LLM and no API key.

- **Replay engine.** Play, pause, reset, 0.25x to 10x speed, seek in both directions and jump-to-time. Each user gets a private replay. Events are delivered over WebSocket (SSE is kept for the older endpoint). The scheduler wakes exactly when the next recorded event is due, so there is no fixed polling delay.
- **Time-aware SQL analytics.** 28 question types are answered by parameterised SQL using CTEs, joins, window functions, `GROUP BY`/`HAVING`, subqueries, `CASE` and set operations. Follow-ups such as "compare him with the second-fastest" work. Penalty questions are matched on the "(CODE)" in the steward text, because OpenF1 leaves `driver_id` empty on every race-control message.
- **Dashboard.** The existing panels switch to replay data while a replay runs. New sections: broadcast view with a Pit Wall chat, replay controls, race overview, SQL analytics, six live charts and recording sync.

## How the future stays hidden

- The query is validated on the syntax tree, with function and table allow-lists.
- It runs as a read-only database role, in a read-only transaction with a timeout and a row cap.
- The role can only read time-bounded `replay.*` views.
- The replay clock can only be moved with a secret held by the backend.
- The question text never reaches the SQL.

## Database changes

- `queries/13_replay_time_aware.sql`: adds `laps.lap_start_at` and `laps.lap_end_at` with indexes, creates the `replay` schema with 11 views, and creates the `ramp_readonly` role.
- `queries/14_replay_time_aware_undo.sql`: reverses it.
- `F1_Schema.sql` is untouched. The migration is already applied.
- Data: the 20 races of 2026 up to Nov 8 are imported, with lap start times, positions and gaps.

To reproduce on a fresh database:

```bash
python backend/apply_replay_sql.py              # add --dry-run to test, --down to undo
F1_BACKFILL=1 python backend/import_f1.py       # PowerShell: $env:F1_BACKFILL=1
```

## Endpoints

Replay:
- `GET /api/replay/sessions`, `GET /api/replay/state`
- `POST /api/replay/start`, `/play`, `/resume`, `/pause`, `/reset`, `/speed`, `/seek`
- `DELETE /api/replay/{replay_id}`
- `GET /api/replay/stream` (SSE), `GET /api/replay/analytics`
- `WS /ws/replay`

Analytics:
- `POST /api/analytics/query`, `POST /api/analytics/explain`
- `GET /api/analytics/history`, `GET /api/analytics/intents`
- `WS /ws/analytics`

All existing `/api/*` and `/api/demo/*` routes are unchanged.

## Environment variables

In `.env`:

| Variable | Purpose |
|---|---|
| `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` | Admin database connection |
| `RAMP_RO_USER`, `RAMP_RO_PASSWORD` | Read-only analytics role |
| `REPLAY_CLOCK_SECRET` | Secret that lets the backend move a connection's replay clock |

Optional: `CORS_ORIGINS` (extra dev origins), `VITE_API_URL` (frontend API address).

Importer: `F1_YEAR` (default 2026), `F1_END_DATE` (default 2026-11-08), `F1_BACKFILL`, `F1_FORCE`, `OPENF1_DELAY`.

## Files

Edited:
- `backend/main.py`, `backend/backend/main.py` (routers, CORS)
- `backend/import_f1.py` (2026 range, retries, positions and intervals, backfill mode)
- `backend/requirements.txt`, `backend/backend/requirements.txt` (`sqlglot`)
- `.env.example`
- `frontend/src/App.jsx`, `frontend/src/api.js`

New backend (`backend/backend/`):
- Replay: `replay.py`, `replay_clock.py`, `replay_state.py`, `replay_scheduler.py`, `replay_service.py`, `replay_routes.py`, `websocket_manager.py`, `replay_analytics.py`
- SQL analytics: `sql_validator.py`, `query_executor.py`, `sql_generator.py`, `intent_parser.py`, `analytics_service.py`, `analytics_routes.py`
- Docs: `REPLAY_LEAKS.md`
- 9 test files in `tests/`

Other new files: `backend/apply_replay_sql.py`, `queries/13_replay_time_aware.sql`, `queries/14_replay_time_aware_undo.sql`.

New frontend (`frontend/src/`):
- Hooks: `useReplay.js`, `useAnalytics.js`, `useVideoSync.js`
- Components: `BroadcastStage.jsx`, `PitWall.jsx`, `ReplayControls.jsx`, `RaceOverview.jsx`, `SqlAnalytics.jsx`, `VisualAnalytics.jsx`, `AnalyticsChart.jsx`, `VideoSync.jsx`
- Model, styles, tests: `replayModel.js`, `replayModel.test.js`, `Replay.css`

## Testing

- Backend: 169 tests pass. They cover the clock, scheduler, validator (injection and mutation cases), executor permissions, the replay views matching the emitted events, every question type against the real database with no future timestamps, follow-ups, caching, multi-user isolation and the WebSocket.
- Frontend: 11 model tests pass. Lint is clean and the build succeeds.
- Browser: checked live on the 2026 Australia GP at 10x (seek, reset, follow-up question, time-bounded panels, charts, phone layout).

## How to run

1. Make sure PostgreSQL is running (service `postgresql-x64-18`).
2. Install dependencies into your venv (repo root):
   ```bash
   .\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
   ```
3. Start the backend. It must be the top-level `main.py`, run from `backend/`:
   ```bash
   cd backend
   ..\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
   ```
4. Start the frontend in a second terminal:
   ```bash
   cd frontend
   npm run dev
   ```
5. Open `http://localhost:5173`, pick a race, press **Start replay**, then ask the Pit Wall a question.

Tests:

```bash
cd backend && ..\.venv\Scripts\python.exe -m pytest backend/tests -q
cd frontend && node --test src/replayModel.test.js
```

## Limits

- No qualifying or grid data is stored; answers say so.
- OpenF1's 2026 pit-stop data is thin; answers say so.
- No car telemetry or location data; nothing is faked.
- Replays live in memory, so they need a single backend process.
- Questions outside the 28 supported types get suggestions, not a free-form answer.
- Servers started before these changes (ports 8000 and 5173) need `pip install -r backend/requirements.txt` and a restart.

## Next

The UI is planned to become a desktop overlay: a transparent, always-on-top window over the stream. The backend and React logic carry over; the window shell and the sync approach are new. Open questions: Electron or Tauri, which stream, what the overlay shows, and whether the browser dashboard stays.
