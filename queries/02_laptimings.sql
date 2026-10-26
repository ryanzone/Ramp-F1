SELECT
    d.driver_code,
    l.lap_number,
    l.lap_time_seconds,
    l.sector1_seconds,
    l.sector2_seconds,
    l.sector3_seconds,
    l.speed_trap_kmh
FROM laps l
JOIN session_drivers sd
    ON sd.session_driver_id = l.session_driver_id
JOIN drivers d
    ON d.driver_id = sd.driver_id
ORDER BY d.driver_code, l.lap_number
LIMIT 100;