SELECT
    d.driver_code,
    p.lap_number,
    p.stop_number,
    p.lane_duration_seconds,
    p.stop_duration_seconds,
    p.pit_timestamp
FROM pit_stops p
JOIN session_drivers sd
    ON sd.session_driver_id = p.session_driver_id
JOIN drivers d
    ON d.driver_id = sd.driver_id
ORDER BY p.lap_number, d.driver_code;