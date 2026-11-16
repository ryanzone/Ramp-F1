SELECT
    d.driver_code,
    d.driver_name,
    t.team_name,
    COUNT(DISTINCT p.pit_stop_id) AS recorded_stops,
    GREATEST(COALESCE(MAX(ts.stint_number), 1) - 1, 0)
        AS stops_from_tyre_stints
FROM session_drivers sd
JOIN drivers d
    ON sd.driver_id = d.driver_id
LEFT JOIN teams t
    ON sd.team_id = t.team_id
LEFT JOIN pit_stops p
    ON p.session_driver_id = sd.session_driver_id
LEFT JOIN tyre_stints ts
    ON ts.session_driver_id = sd.session_driver_id
GROUP BY
    sd.session_driver_id,
    d.driver_code,
    d.driver_name,
    t.team_name
ORDER BY
    stops_from_tyre_stints DESC,
    recorded_stops DESC,
    d.driver_code;