# Role A demo — ready to run

Run all commands from the repository root (the folder containing F1_Schema.sql).

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000/demo and select a driver. Open http://127.0.0.1:8000/docs to demonstrate the JSON endpoints under /api/demo. No database or internet is required for the included snapshot. Existing /api/races, /api/laps, etc. still use your team's PostgreSQL database. The React prototype is unchanged; this small demo page demonstrates A's real pipeline without claiming the rest of the dashboard is connected.

## What to present

1. Show the saved real race, driver count, accepted laps and rejected count.
2. Choose a driver to display actual lap durations served by FastAPI.
3. Show backend/demo_data/raw: unmodified parsed source payloads plus request/fetch metadata.
4. Show backend/demo_data/processed/9165.json: cleaned laps and rejection report.
5. If PostgreSQL is configured, run the optional load below, then show /api/races and /api/laps.

Included data: Singapore 2023 session 9165, fetched on October 27: 19 source driver records and 1,091 accepted laps. Missing upstream drivers are not invented. This is deliberately labelled as Singapore, not Abu Dhabi.

## Refresh to the team's Abu Dhabi 2025 race

```powershell
.\.venv\Scripts\python.exe -m backend.demo fetch
```

Fetch targets session 9839, checks that the race is historical, retrieves meeting/drivers/laps, retains raw snapshots and validates lap records. The active demo changes only on success. On October 31 OpenF1 returned HTTP 401 stating that a live session temporarily restricts ALL API access, including historical requests, to authenticated users. Retry after the live window; the included snapshot continues working. Live access is not promised to be free. Sources: https://openf1.org/docs/ and the actual API response recorded in VERIFICATION.md.

## Optional PostgreSQL load

Copy .env.example to .env and set your existing DB credentials. For a NEW empty database only, execute your team's F1_Schema.sql once. Do not rerun that creation script on existing tables. Then:

```powershell
.\.venv\Scripts\python.exe -m backend.demo load
```

Uses exactly the existing schema and DB_* variables. The loader is a scoped adaptation of import_f1.py: generated IDs, existing drivers/teams/session links, lap upserts, null round number when unknown, validation-derived is_valid and raw_api_data provenance. Original import scripts remain available. Run one import at a time; name-based circuit/race reconciliation is intended for this demo, not a general multi-season identity service. Raw provenance is added in a second transaction after the core import; rerunning completes it if that step fails. Core upserts do not delete existing other entities.

## Scope and integration

Changed existing files: backend/main.py (register demo router and defer optional database imports), backend/requirements.txt (fetch/validation dependencies). Added backend/demo*.py, backend/demo_data/, .env.example and these instructions. No schema migration and no frontend changes are required. Copy these files into your team checkout, review git diff, and commit normally. The accompanying changes-only ZIP contains exactly those paths. Full checkout base revision is in VERIFICATION.md.

Core scope: historical sessions, drivers/laps, validation, raw retention, API serving and optional PostgreSQL load. Tyres, pit stops, weather, results, event detection and live streaming are left to later milestones/the team's existing code. is_valid is pace eligibility (known positive duration and explicitly not a pit-out lap), not official FIA lap legality. Incomplete durations remain null; bad types, negative/nonfinite times, unknown drivers and duplicate lap keys are reported. The newer ERD is already represented by F1_Schema.sql; we do not replace it.

Tests: python -m unittest discover -s backend/tests -v
