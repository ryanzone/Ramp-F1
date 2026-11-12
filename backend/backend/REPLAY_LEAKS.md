# Replay: where analytics would leak future data

Replay serves a finished race as if it were live. Anything computed over the
whole session, or anything that exposes an outcome, shows the future. Replay
analytics (`replay_analytics.py`) therefore never touch PostgreSQL or the
views below; they run in Python over events with `t <= replay clock`.

## SQL that must NOT run during replay

| Object | Why it leaks |
|---|---|
| `queries/08_lap_pace_analysis.sql` `v_lap_pace_analysis` | Computed over every lap in `laps`. The rolling window only looks backwards, but `laps` has **no timestamp**, so rows cannot be limited to "laps finished by the clock". Selecting from it returns the whole race. |
| `queries/09_anomaly_detection.sql` | `INSERT`s whole-session results into `detected_events`. The table's only time column, `detected_at`, is wall-clock insert time, not race time, so anomalies from lap 60 are indistinguishable from lap 5. It also writes persistent rows (side effect). |
| `queries/10_analytics_testing.sql` | Reads `v_lap_pace_analysis`, `pit_stops` and `detected_events` unfiltered (totals, averages, all anomalies). |

## Existing `/api/*` endpoints (kept working, but not replay-safe)

(`backend/main.py`, the v1.1.0 DB-backed API)

| Endpoint | Leak |
|---|---|
| `/api/races` | `race_distance_laps` = `MAX(lap_number)` reveals the total race length. |
| `/api/results` | Final classification, DNF/DNS/DSQ. |
| `/api/tyre-stints` | `end_lap` / `stint_laps` reveal future pit stops and stint lengths. |
| `/api/laps` | Returns every lap of the race (no time bound). |
| `/api/pit-stops` | Returns every stop, including future ones. |
| `/api/race-control`, `/api/weather` | Accept only `limit`; return the whole session. `weather` is ordered newest-first. |

The replay page must use `/api/replay/*` only.

## Leaks found and fixed inside replay itself

- Lap duration is attached to `lap_complete` (at `date_start + lap_duration`),
  never to `lap_start`.
- A pit stop is stamped at pit **exit** (entry + lane duration), because its
  durations are unknown at entry.

## Not leak-proof yet (decisions needed if added)

- `tyre_stints`, `positions`, `overtakes`, `session_results` are not replayed.
  Stint end laps, gaps and results would need the same treatment (event stamped
  when it becomes knowable).

## Migration proposal (NOT applied; `F1_Schema.sql` is unchanged)

To replay straight from PostgreSQL, `laps` needs a start time:

```sql
ALTER TABLE laps ADD COLUMN lap_start_at TIMESTAMPTZ;
CREATE INDEX idx_laps_start ON laps (lap_start_at);
```

`backend/import_f1.py` would also have to store OpenF1 `date_start` into it.
With that, a clock-bounded view filters on
`lap_start_at + lap_time_seconds * interval '1 second' <= :replay_time`
(and `detected_events` would need a race-time column instead of `detected_at`).
Until you approve this, replay reads the saved JSON snapshot only.
