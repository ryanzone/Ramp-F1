SELECT
    rc.recorded_at AS event_time,
    'race control' AS kind,
    rc.message AS detail
FROM race_control_events rc
WHERE rc.recorded_at >= CURRENT_TIMESTAMP - (30 * INTERVAL '1 minute')

UNION ALL

SELECT
    p.pit_timestamp AS event_time,
    'pit stop' AS kind,
    d.driver_code || ' entered the pits (lap ' || p.lap_number || ')' AS detail
FROM pit_stops p
JOIN session_drivers sd
    ON p.session_driver_id = sd.session_driver_id
JOIN drivers d
    ON sd.driver_id = d.driver_id
WHERE p.pit_timestamp >= CURRENT_TIMESTAMP - (30 * INTERVAL '1 minute')

ORDER BY event_time DESC
LIMIT 20;