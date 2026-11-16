SELECT
    d.driver_number,
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
WHERE sd.session_id = 1
ORDER BY d.driver_number, ts.stint_number;