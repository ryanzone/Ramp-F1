SELECT
    d.driver_code,
    d.driver_name,
    t.team_name,
    ts.compound,
    ts.stint_number,
    ts.start_lap,
    COALESCE(ts.starting_tyre_age, 0)
        + COALESCE(ts.end_lap, ts.start_lap) - ts.start_lap
        AS tyre_age_laps,
    p.position
FROM tyre_stints ts
JOIN session_drivers sd
    ON ts.session_driver_id = sd.session_driver_id
JOIN drivers d
    ON sd.driver_id = d.driver_id
LEFT JOIN teams t
    ON sd.team_id = t.team_id
LEFT JOIN positions p
    ON p.session_driver_id = sd.session_driver_id
WHERE UPPER(ts.compound) = 'SOFT'
ORDER BY ts.compound, p.position;