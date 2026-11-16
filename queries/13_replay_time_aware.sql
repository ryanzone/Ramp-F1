-- ---- 1. Timestamp columns on laps -------------------------------------------
-- OpenF1 gives each lap a date_start; laps previously stored only durations.
ALTER TABLE laps ADD COLUMN IF NOT EXISTS lap_start_at TIMESTAMPTZ;
ALTER TABLE laps ADD COLUMN IF NOT EXISTS lap_end_at   TIMESTAMPTZ;   -- derived, see replay.refresh_lap_end_times

CREATE INDEX IF NOT EXISTS idx_laps_driver_end_at   ON laps (session_driver_id, lap_end_at);
CREATE INDEX IF NOT EXISTS idx_laps_driver_start_at ON laps (session_driver_id, lap_start_at);
CREATE INDEX IF NOT EXISTS idx_pit_stops_timestamp  ON pit_stops (pit_timestamp);
CREATE INDEX IF NOT EXISTS idx_weather_session_time ON weather_samples (session_id, recorded_at);

-- ---- 2. Replay schema (recreated on every run, so this file is re-runnable) --
DROP SCHEMA IF EXISTS replay CASCADE;
CREATE SCHEMA replay;

-- The clock lives in a table the read-only role cannot touch. Rows are keyed by
-- backend pid so concurrent users (separate connections) never share a clock.
CREATE TABLE replay.clock_secret (secret TEXT NOT NULL);
INSERT INTO replay.clock_secret (secret) VALUES ({{CLOCK_SECRET}});

CREATE UNLOGGED TABLE replay.clock (
    backend_pid INT PRIMARY KEY,
    session_id  BIGINT NOT NULL,
    replay_time TIMESTAMPTZ NOT NULL,
    set_at      TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

-- Only a caller that knows the secret can move the clock. The secret is held by
-- the backend (.env), so SQL running inside a replay query cannot change it.
CREATE FUNCTION replay.set_clock(p_secret TEXT, p_session_id BIGINT, p_time TIMESTAMPTZ)
RETURNS VOID LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, replay AS $$
BEGIN
    IF p_secret IS DISTINCT FROM (SELECT secret FROM replay.clock_secret LIMIT 1) THEN
        RAISE EXCEPTION 'invalid replay clock secret' USING ERRCODE = '42501';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM public.sessions WHERE session_id = p_session_id) THEN
        RAISE EXCEPTION 'unknown session %', p_session_id;
    END IF;
    INSERT INTO replay.clock (backend_pid, session_id, replay_time)
    VALUES (pg_backend_pid(), p_session_id, p_time)
    ON CONFLICT (backend_pid) DO UPDATE
        SET session_id = EXCLUDED.session_id, replay_time = EXCLUDED.replay_time, set_at = clock_timestamp();
END $$;

CREATE FUNCTION replay.replay_time() RETURNS TIMESTAMPTZ
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog, replay AS $$
DECLARE t TIMESTAMPTZ;
BEGIN
    SELECT replay_time INTO t FROM replay.clock WHERE backend_pid = pg_backend_pid();
    IF t IS NULL THEN RAISE EXCEPTION 'replay clock is not set for this connection'; END IF;
    RETURN t;
END $$;

CREATE FUNCTION replay.replay_session() RETURNS BIGINT
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog, replay AS $$
DECLARE s BIGINT;
BEGIN
    SELECT session_id INTO s FROM replay.clock WHERE backend_pid = pg_backend_pid();
    IF s IS NULL THEN RAISE EXCEPTION 'replay session is not set for this connection'; END IF;
    RETURN s;
END $$;

-- Derives lap_end_at for one session: start + duration, else the next lap's start.
-- Mirrors backend/replay.py. Run by the importer after lap_start_at is stored.
CREATE FUNCTION replay.refresh_lap_end_times(p_session_id BIGINT) RETURNS INT
LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
DECLARE n INT;
BEGIN
    WITH nxt AS (
        SELECT l.lap_id, l.lap_number, l.lap_start_at, l.lap_time_seconds,
               LEAD(l.lap_number)   OVER w AS next_no,
               LEAD(l.lap_start_at) OVER w AS next_start
        FROM laps l JOIN session_drivers sd ON sd.session_driver_id = l.session_driver_id
        WHERE sd.session_id = p_session_id
        WINDOW w AS (PARTITION BY l.session_driver_id ORDER BY l.lap_number)
    ), calc AS (
        SELECT lap_id,
               CASE WHEN lap_start_at IS NULL THEN NULL
                    WHEN lap_time_seconds > 0 THEN lap_start_at + make_interval(secs => lap_time_seconds::float8)
                    WHEN next_no = lap_number + 1 AND next_start > lap_start_at THEN next_start
               END AS end_at
        FROM nxt
    )
    UPDATE laps l SET lap_end_at = c.end_at
    FROM calc c
    WHERE c.lap_id = l.lap_id AND l.lap_end_at IS DISTINCT FROM c.end_at;
    GET DIAGNOSTICS n = ROW_COUNT;
    RETURN n;
END $$;

-- ---- 3. Time-bounded views ---------------------------------------------------
-- Every view is limited to the clock's session and to rows known at replay_time.
-- (SELECT replay.replay_time()) makes the planner evaluate the clock once.

CREATE VIEW replay.session_info AS
SELECT s.session_id, r.race_id, r.season, r.round_number, r.race_name,
       c.circuit_name, c.country, s.session_type, s.session_date,
       (SELECT replay.replay_time()) AS replay_time
FROM sessions s
JOIN races r    ON r.race_id = s.race_id
JOIN circuits c ON c.circuit_id = r.circuit_id
WHERE s.session_id = (SELECT replay.replay_session());

CREATE VIEW replay.drivers AS
SELECT sd.session_driver_id, d.driver_id, d.driver_number, d.driver_code, d.driver_name, t.team_name
FROM session_drivers sd
JOIN drivers d ON d.driver_id = sd.driver_id
LEFT JOIN teams t ON t.team_id = sd.team_id
WHERE sd.session_id = (SELECT replay.replay_session());

-- Only laps that have been completed by the replay time.
CREATE VIEW replay.laps AS
SELECT dr.session_driver_id, dr.driver_number, dr.driver_code, dr.driver_name, dr.team_name,
       l.lap_number, l.lap_start_at, l.lap_end_at, l.lap_time_seconds,
       l.sector1_seconds, l.sector2_seconds, l.sector3_seconds, l.speed_trap_kmh, l.is_valid
FROM laps l
JOIN replay.drivers dr ON dr.session_driver_id = l.session_driver_id
WHERE l.lap_end_at <= (SELECT replay.replay_time());

-- A stint is visible once the driver has started a lap in it; its end_lap stays
-- NULL (still running) until that lap has actually been completed.
CREATE VIEW replay.tyre_stints AS
SELECT dr.session_driver_id, dr.driver_number, dr.driver_code, dr.driver_name, dr.team_name,
       ts.stint_number, ts.compound, ts.start_lap,
       CASE WHEN ts.end_lap IS NOT NULL AND EXISTS (
                SELECT 1 FROM laps e
                WHERE e.session_driver_id = ts.session_driver_id AND e.lap_number = ts.end_lap
                  AND e.lap_end_at <= (SELECT replay.replay_time()))
            THEN ts.end_lap END AS end_lap,
       ts.starting_tyre_age,
       (SELECT COUNT(*)::INT FROM laps c
         WHERE c.session_driver_id = ts.session_driver_id
           AND c.lap_number >= ts.start_lap
           AND (ts.end_lap IS NULL OR c.lap_number <= ts.end_lap)
           AND c.lap_end_at <= (SELECT replay.replay_time())) AS laps_completed
FROM tyre_stints ts
JOIN replay.drivers dr ON dr.session_driver_id = ts.session_driver_id
WHERE EXISTS (SELECT 1 FROM laps s
              WHERE s.session_driver_id = ts.session_driver_id
                AND s.lap_number >= ts.start_lap
                AND s.lap_start_at <= (SELECT replay.replay_time()));

-- A stop is visible once the car has left the pit lane (entry + lane time), since
-- the durations are only known then. Stops without a timestamp are never shown.
CREATE VIEW replay.pit_stops AS
SELECT dr.session_driver_id, dr.driver_number, dr.driver_code, dr.driver_name, dr.team_name,
       ps.lap_number, ps.stop_number, ps.pit_timestamp AS pit_entry_at,
       ps.pit_timestamp + make_interval(secs => COALESCE(ps.lane_duration_seconds, 0)::float8) AS pit_exit_at,
       ps.lane_duration_seconds, ps.stop_duration_seconds
FROM pit_stops ps
JOIN replay.drivers dr ON dr.session_driver_id = ps.session_driver_id
WHERE ps.pit_timestamp + make_interval(secs => COALESCE(ps.lane_duration_seconds, 0)::float8)
      <= (SELECT replay.replay_time());

CREATE VIEW replay.race_control AS
SELECT rc.recorded_at, rc.lap_number, rc.category, rc.flag, rc.scope, rc.sector, rc.message,
       dr.driver_number, dr.driver_code
FROM race_control_events rc
LEFT JOIN replay.drivers dr ON dr.driver_id = rc.driver_id
WHERE rc.session_id = (SELECT replay.replay_session())
  AND rc.recorded_at <= (SELECT replay.replay_time());

CREATE VIEW replay.weather AS
SELECT w.recorded_at, w.air_temperature, w.track_temperature, w.humidity, w.rainfall, w.wind_speed
FROM weather_samples w
WHERE w.session_id = (SELECT replay.replay_session())
  AND w.recorded_at <= (SELECT replay.replay_time());

CREATE VIEW replay.positions AS
SELECT dr.session_driver_id, dr.driver_number, dr.driver_code, dr.team_name,
       p.recorded_at, p.position, p.gap_to_leader_seconds, p.interval_ahead_seconds
FROM positions p
JOIN replay.drivers dr ON dr.session_driver_id = p.session_driver_id
WHERE p.recorded_at <= (SELECT replay.replay_time());

-- Latest known position and latest known gap/interval per driver at replay time.
CREATE VIEW replay.current_positions AS
SELECT dr.session_driver_id, dr.driver_number, dr.driver_code, dr.driver_name, dr.team_name,
       pos.position, pos.recorded_at AS position_at,
       gap.gap_to_leader_seconds, gap.interval_ahead_seconds, gap.recorded_at AS gap_at
FROM replay.drivers dr
LEFT JOIN LATERAL (
    SELECT p.position, p.recorded_at FROM positions p
    WHERE p.session_driver_id = dr.session_driver_id AND p.position IS NOT NULL
      AND p.recorded_at <= (SELECT replay.replay_time())
    ORDER BY p.recorded_at DESC LIMIT 1) pos ON TRUE
LEFT JOIN LATERAL (
    SELECT p.gap_to_leader_seconds, p.interval_ahead_seconds, p.recorded_at FROM positions p
    WHERE p.session_driver_id = dr.session_driver_id
      AND (p.gap_to_leader_seconds IS NOT NULL OR p.interval_ahead_seconds IS NOT NULL)
      AND p.recorded_at <= (SELECT replay.replay_time())
    ORDER BY p.recorded_at DESC LIMIT 1) gap ON TRUE;

-- Per-driver pace over completed valid laps (window function ranks recency).
CREATE VIEW replay.driver_pace AS
WITH valid AS (
    SELECT * FROM replay.laps WHERE is_valid AND lap_time_seconds IS NOT NULL
), ranked AS (
    SELECT valid.*, ROW_NUMBER() OVER (PARTITION BY session_driver_id ORDER BY lap_number DESC) AS recency
    FROM valid
)
SELECT session_driver_id, driver_number, driver_code, driver_name, team_name,
       COUNT(*)::INT AS valid_laps,
       ROUND(AVG(lap_time_seconds), 3)                                   AS avg_lap,
       MIN(lap_time_seconds)                                             AS best_lap,
       ROUND(STDDEV_SAMP(lap_time_seconds), 3)                           AS lap_stddev,
       ROUND(AVG(lap_time_seconds) FILTER (WHERE recency <= 5), 3)       AS avg_last5,
       MAX(lap_number)                                                   AS last_lap_number
FROM ranked
GROUP BY session_driver_id, driver_number, driver_code, driver_name, team_name;

-- Each driver's stint that is still running at replay time.
CREATE VIEW replay.current_stints AS
SELECT * FROM replay.tyre_stints WHERE end_lap IS NULL;

-- ---- 4. Read-only role -------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ramp_readonly') THEN
        EXECUTE format('CREATE ROLE ramp_readonly LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE', {{RO_PASSWORD}});
    ELSE
        EXECUTE format('ALTER ROLE ramp_readonly LOGIN PASSWORD %L', {{RO_PASSWORD}});
    END IF;
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO ramp_readonly', current_database());
END $$;

-- The role sees only the replay schema: unqualified names resolve to replay.*.
ALTER ROLE ramp_readonly SET search_path = replay, pg_catalog;
ALTER ROLE ramp_readonly SET statement_timeout = '5s';
ALTER ROLE ramp_readonly SET lock_timeout = '1s';
ALTER ROLE ramp_readonly SET idle_in_transaction_session_timeout = '15s';

REVOKE ALL ON ALL TABLES IN SCHEMA public FROM ramp_readonly;
GRANT USAGE ON SCHEMA replay TO ramp_readonly;
GRANT SELECT ON replay.session_info, replay.drivers, replay.laps, replay.tyre_stints,
                replay.pit_stops, replay.race_control, replay.weather, replay.positions,
                replay.current_positions, replay.driver_pace, replay.current_stints
      TO ramp_readonly;

REVOKE ALL ON FUNCTION replay.set_clock(TEXT, BIGINT, TIMESTAMPTZ) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION replay.set_clock(TEXT, BIGINT, TIMESTAMPTZ) TO ramp_readonly;
REVOKE ALL ON FUNCTION replay.refresh_lap_end_times(BIGINT) FROM PUBLIC;
