SELECT
    RANK() OVER (ORDER BY l.lap_time_seconds) AS lap_rank,
    d.driver_code,
    d.driver_name,
    t.team_name,
    l.lap_number,
    l.lap_time_seconds
FROM laps l
JOIN session_drivers sd
    ON l.session_driver_id = sd.session_driver_id
JOIN drivers d
    ON sd.driver_id = d.driver_id
LEFT JOIN teams t
    ON sd.team_id = t.team_id
WHERE l.is_valid = TRUE
  AND l.lap_time_seconds IS NOT NULL
ORDER BY l.lap_time_seconds
LIMIT 10;