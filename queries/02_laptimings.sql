SELECT
    d.driver_number,
    d.driver_code,
    l.lap_number,
    l.lap_start_at,
    l.lap_end_at,
    l.lap_time_seconds,
    l.sector1_seconds,
    l.sector2_seconds,
    l.sector3_seconds,
    l.speed_trap_kmh,
    l.is_valid
FROM laps l
JOIN session_drivers sd
    ON sd.session_driver_id = l.session_driver_id
JOIN drivers d
    ON d.driver_id = sd.driver_id
WHERE sd.session_id = 1
  AND l.lap_start_at IS NOT NULL
ORDER BY l.lap_start_at;