
CREATE TABLE circuits (
    circuit_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    circuit_name VARCHAR(120) NOT NULL,
    country VARCHAR(80),
    circuit_location VARCHAR(100)
);

CREATE TABLE races (
    race_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    season INT NOT NULL,
    round_number INT,
    race_name VARCHAR(120) NOT NULL,
    circuit_id BIGINT NOT NULL REFERENCES circuits(circuit_id),
    race_date DATE,
    UNIQUE (season, round_number)
);

CREATE TABLE sessions (
    session_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    race_id BIGINT NOT NULL REFERENCES races(race_id),
    session_type VARCHAR(20),
    session_date TIMESTAMPTZ,
    source_session_key BIGINT UNIQUE,
    status VARCHAR(20)
);

CREATE TABLE teams (
    team_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    team_name VARCHAR(100) UNIQUE NOT NULL
);

CREATE TABLE drivers (
    driver_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    driver_number INT,
    driver_code VARCHAR(10),
    driver_name VARCHAR(100) NOT NULL
);

CREATE TABLE session_drivers (
    session_driver_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    session_id BIGINT NOT NULL REFERENCES sessions(session_id),
    driver_id BIGINT NOT NULL REFERENCES drivers(driver_id),
    team_id BIGINT REFERENCES teams(team_id),
    UNIQUE (session_id, driver_id)
);

CREATE TABLE weather_samples (
    weather_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    session_id BIGINT NOT NULL REFERENCES sessions(session_id),
    recorded_at TIMESTAMPTZ,
    air_temperature NUMERIC,
    track_temperature NUMERIC,
    humidity NUMERIC,
    rainfall BOOLEAN,
    wind_speed NUMERIC
);

CREATE TABLE raw_api_data (
    raw_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    session_id BIGINT REFERENCES sessions(session_id),
    endpoint VARCHAR(200) NOT NULL,
    fetched_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    payload JSONB NOT NULL
);

CREATE TABLE race_control_events (
    race_control_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    session_id BIGINT NOT NULL REFERENCES sessions(session_id),
    driver_id BIGINT REFERENCES drivers(driver_id),
    recorded_at TIMESTAMPTZ NOT NULL,
    lap_number INT,
    category VARCHAR(100),
    flag VARCHAR(50),
    scope VARCHAR(50),
    sector INT,
    message TEXT
);

CREATE TABLE overtakes (
    overtake_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    session_id BIGINT NOT NULL REFERENCES sessions(session_id),
    overtaking_driver_id BIGINT NOT NULL REFERENCES drivers(driver_id),
    overtaken_driver_id BIGINT NOT NULL REFERENCES drivers(driver_id),
    recorded_at TIMESTAMPTZ NOT NULL,
    position_after INT,
    CHECK (overtaking_driver_id <> overtaken_driver_id)
);

CREATE TABLE laps (
    lap_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    session_driver_id BIGINT NOT NULL
        REFERENCES session_drivers(session_driver_id),
    lap_number INT NOT NULL CHECK (lap_number > 0),
    lap_time_seconds NUMERIC,
    sector1_seconds NUMERIC,
    sector2_seconds NUMERIC,
    sector3_seconds NUMERIC,
    speed_trap_kmh NUMERIC,
    is_valid BOOLEAN DEFAULT TRUE,
    UNIQUE (session_driver_id, lap_number)
);

CREATE TABLE tyre_stints (
    stint_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    session_driver_id BIGINT NOT NULL
        REFERENCES session_drivers(session_driver_id),
    stint_number INT NOT NULL,
    compound VARCHAR(20),
    start_lap INT NOT NULL,
    end_lap INT,
    starting_tyre_age INT,
    CHECK (end_lap IS NULL OR end_lap >= start_lap),
    UNIQUE (session_driver_id, stint_number)
);

CREATE TABLE pit_stops (
    pit_stop_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    session_driver_id BIGINT NOT NULL
        REFERENCES session_drivers(session_driver_id),
    lap_number INT,
    stop_number INT,
    lane_duration_seconds NUMERIC,
    stop_duration_seconds NUMERIC,
    pit_timestamp TIMESTAMPTZ,
    UNIQUE (session_driver_id, stop_number)
);

CREATE TABLE positions (
    position_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    session_driver_id BIGINT NOT NULL
        REFERENCES session_drivers(session_driver_id),
    recorded_at TIMESTAMPTZ NOT NULL,
    position INT,
    gap_to_leader_seconds NUMERIC,
    interval_ahead_seconds NUMERIC,
    UNIQUE (session_driver_id, recorded_at)
);

CREATE TABLE detected_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    session_driver_id BIGINT NOT NULL
        REFERENCES session_drivers(session_driver_id),
    lap_number INT,
    event_type VARCHAR(50) NOT NULL,
    severity VARCHAR(20) NOT NULL,
    trigger_metric VARCHAR(50),
    observed_value NUMERIC,
    baseline_value NUMERIC,
    deviation NUMERIC,
    description TEXT,
    detected_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE session_results (
    result_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    session_driver_id BIGINT NOT NULL UNIQUE
        REFERENCES session_drivers(session_driver_id),
    grid_position INT,
    final_position INT,
    number_of_laps INT,
    duration_seconds NUMERIC,
    gap_to_leader NUMERIC,
    dnf BOOLEAN DEFAULT FALSE,
    dns BOOLEAN DEFAULT FALSE,
    dsq BOOLEAN DEFAULT FALSE
);

CREATE INDEX idx_races_season ON races(season);
CREATE INDEX idx_sessions_race ON sessions(race_id);
CREATE INDEX idx_session_drivers_driver ON session_drivers(driver_id);
CREATE INDEX idx_laps_driver_lap ON laps(session_driver_id, lap_number);
CREATE INDEX idx_pit_stops_driver ON pit_stops(session_driver_id);
CREATE INDEX idx_positions_driver_time ON positions(session_driver_id, recorded_at);
CREATE INDEX idx_race_control_session_time ON race_control_events(session_id, recorded_at);
CREATE INDEX idx_overtakes_session_time ON overtakes(session_id, recorded_at);
CREATE INDEX idx_detected_events_severity ON detected_events(severity);
