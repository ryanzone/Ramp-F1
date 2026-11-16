SELECT
    t.team_name,
    ROUND(AVG(l.lap_time_seconds)::NUMERIC, 3) AS avg_lap_seconds,
    ROUND(MIN(l.lap_time_seconds)::NUMERIC, 3) AS fastest_lap_seconds,
    COUNT(l.lap_number) AS total_valid_laps
FROM teams t
JOIN session_drivers sd
    ON t.team_id = sd.team_id
JOIN drivers d
    ON sd.driver_id = d.driver_id
LEFT JOIN laps l
    ON sd.session_driver_id = l.session_driver_id
    AND l.is_valid = TRUE
    AND l.lap_time_seconds > 0
    AND l.lap_time_seconds < 300
GROUP BY t.team_name
ORDER BY avg_lap_seconds ASC NULLS LAST;