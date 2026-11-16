SELECT
    t.team_name,
    COUNT(p.stop_number) AS total_pit_stops,
    ROUND(AVG(p.stop_duration_seconds)::NUMERIC, 3)
        AS avg_pit_duration_seconds,
    ROUND(MIN(p.stop_duration_seconds)::NUMERIC, 3)
        AS fastest_pit_seconds
FROM teams t
JOIN session_drivers sd
    ON t.team_id = sd.team_id
JOIN drivers d
    ON sd.driver_id = d.driver_id
LEFT JOIN pit_stops p
    ON sd.session_driver_id = p.session_driver_id
GROUP BY t.team_name
ORDER BY avg_pit_duration_seconds ASC NULLS LAST;