SELECT
    d.driver_code,
    ts.stint_number,
    ts.compound,
    ts.start_lap,
    ts.end_lap,
    ts.starting_tyre_age
FROM tyre_stints ts
JOIN session_drivers sd
    ON sd.session_driver_id = ts.session_driver_id
JOIN drivers d
    ON d.driver_id = sd.driver_id
ORDER BY d.driver_code, ts.stint_number;