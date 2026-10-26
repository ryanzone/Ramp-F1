SELECT
    d.driver_code,
    rc.lap_number,
    rc.category,
    rc.flag,
    rc.scope,
    rc.message,
    rc.recorded_at
FROM race_control_events rc
LEFT JOIN drivers d ON d.driver_id = rc.driver_id
ORDER BY rc.recorded_at;