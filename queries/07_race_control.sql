SELECT
    d.driver_number,
    rc.recorded_at,
    rc.lap_number,
    rc.category,
    rc.flag,
    rc.scope,
    rc.sector,
    rc.message
FROM race_control_events rc
LEFT JOIN drivers d
    ON d.driver_id = rc.driver_id
WHERE rc.session_id = 1
ORDER BY rc.recorded_at;