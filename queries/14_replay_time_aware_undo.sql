-- RAMP 14: undo 13_replay_time_aware.sql. Removes the replay schema, the read-only role and the
-- new laps columns/indexes. Does not touch any other table or row.
DROP SCHEMA IF EXISTS replay CASCADE;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ramp_readonly') THEN
        EXECUTE format('REVOKE CONNECT ON DATABASE %I FROM ramp_readonly', current_database());
        DROP OWNED BY ramp_readonly;
        DROP ROLE ramp_readonly;
    END IF;
END $$;

DROP INDEX IF EXISTS idx_laps_driver_end_at;
DROP INDEX IF EXISTS idx_laps_driver_start_at;
DROP INDEX IF EXISTS idx_pit_stops_timestamp;
DROP INDEX IF EXISTS idx_weather_session_time;
ALTER TABLE laps DROP COLUMN IF EXISTS lap_end_at;
ALTER TABLE laps DROP COLUMN IF EXISTS lap_start_at;
