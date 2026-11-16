SELECT
    d.driver_code,
    p.position,
    p.gap_to_leader_seconds AS gap_to_leader,
    p.interval_ahead_seconds AS interval_ahead
FROM positions p
JOIN session_drivers sd
    ON p.session_driver_id = sd.session_driver_id
JOIN drivers d
    ON sd.driver_id = d.driver_id
WHERE d.driver_code IN ('VER', 'HAM')
ORDER BY p.position;