SELECT
    p.position,
    d.driver_code,
    d.driver_name,
    t.team_name,
    p.gap_to_leader_seconds AS gap_to_leader,
    p.interval_ahead_seconds AS interval_ahead
FROM positions p
JOIN session_drivers sd
    ON p.session_driver_id = sd.session_driver_id
JOIN drivers d
    ON sd.driver_id = d.driver_id
LEFT JOIN teams t
    ON sd.team_id = t.team_id
WHERE p.position IS NOT NULL
ORDER BY p.position
