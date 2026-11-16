SELECT
    MAX(l.lap_number) AS latest_completed_lap,
    COUNT(DISTINCT sd.driver_id) AS drivers_with_laps,
    MIN(p.recorded_at) AS first_lap_finished_at,
    MAX(p.recorded_at) AS latest_lap_finished_at
FROM laps l
JOIN session_drivers sd
    ON l.session_driver_id = sd.session_driver_id
LEFT JOIN positions p
    ON p.session_driver_id = l.session_driver_id;