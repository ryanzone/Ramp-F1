SELECT
    d.driver_code,
    t.team_name,
    ts.stint_number,
    ts.compound,
    ts.start_lap,
    ts.end_lap AS last_lap,
    CASE
        WHEN ts.end_lap IS NULL THEN 'running'
        ELSE 'finished'
    END AS status,
    COALESCE(ts.end_lap, ts.start_lap - 1) - ts.start_lap + 1
        AS laps_completed
FROM tyre_stints ts
JOIN session_drivers sd
    ON ts.session_driver_id = sd.session_driver_id
JOIN drivers d
    ON sd.driver_id = d.driver_id
LEFT JOIN teams t
    ON sd.team_id = t.team_id
ORDER BY t.team_name, d.driver_code, ts.stint_number;