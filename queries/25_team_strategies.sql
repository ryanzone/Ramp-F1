SELECT
    t.team_name,
    d.driver_code,
    STRING_AGG(ts.compound, ' > ' ORDER BY ts.stint_number) AS strategy,
    COUNT(*) AS stints,
    MAX(ts.stint_number) - 1 AS stops_so_far,
    MAX(ts.start_lap) AS latest_stint_start_lap
FROM tyre_stints ts
JOIN session_drivers sd
    ON ts.session_driver_id = sd.session_driver_id
JOIN drivers d
    ON sd.driver_id = d.driver_id
LEFT JOIN teams t
    ON sd.team_id = t.team_id
WHERE t.team_name ILIKE '%Red Bull%'
GROUP BY t.team_name, d.driver_code
ORDER BY t.team_name, d.driver_code;