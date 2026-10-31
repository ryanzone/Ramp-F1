-- =========================================================
-- RAMP: ANALYTICS TESTING
-- =========================================================


-- TEST 1: Check imported lap records

SELECT
    COUNT(*) AS total_laps,
    COUNT(DISTINCT session_driver_id) AS drivers_count,
    COUNT(DISTINCT lap_number) AS different_lap_numbers
FROM laps;


-- TEST 2: Check lap pace analysis

SELECT
    driver_code,
    COUNT(*) AS analysed_laps,
    ROUND(AVG(lap_time_difference), 3)
        AS average_pace_difference
FROM v_lap_pace_analysis
WHERE baseline_lap_count >= 3
GROUP BY driver_code
ORDER BY driver_code;


-- TEST 3: Compare sector performance

SELECT
    driver_code,
    lap_number,
    sector1_difference,
    sector2_difference,
    sector3_difference
FROM v_lap_pace_analysis
WHERE baseline_lap_count >= 3
ORDER BY driver_code, lap_number
LIMIT 50;


-- TEST 4: Check pit-stop records

SELECT
    COUNT(*) AS total_pit_stops,
    ROUND(AVG(stop_duration_seconds), 3)
        AS average_pit_stop_duration
FROM pit_stops
WHERE stop_duration_seconds IS NOT NULL;


-- TEST 5: Count detected anomalies

SELECT
    event_type,
    severity,
    COUNT(*) AS total_events
FROM detected_events
GROUP BY event_type, severity
ORDER BY event_type, severity;


-- TEST 6: Display all detected anomalies

SELECT
    d.driver_code,
    e.lap_number,
    e.event_type,
    e.severity,
    e.observed_value,
    e.baseline_value,
    e.deviation,
    e.description

FROM detected_events e

JOIN session_drivers sd
    ON sd.session_driver_id = e.session_driver_id

JOIN drivers d
    ON d.driver_id = sd.driver_id

ORDER BY e.severity, d.driver_code;