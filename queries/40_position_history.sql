WITH current_positions AS (
    SELECT DISTINCT ON (session_driver_id)
        session_driver_id,
        position
    FROM positions
    WHERE position IS NOT NULL
    ORDER BY session_driver_id, recorded_at DESC
)
SELECT
    r.race_name,
    c.circuit_name,
    d.driver_code,
    l.lap_number,
    cp.position
FROM laps l
JOIN session_drivers sd
    ON l.session_driver_id = sd.session_driver_id
JOIN drivers d
    ON sd.driver_id = d.driver_id
JOIN current_positions cp
    ON cp.session_driver_id = l.session_driver_id
JOIN sessions s
    ON sd.session_id = s.session_id
JOIN races r
    ON s.race_id = r.race_id
JOIN circuits c
    ON r.circuit_id = c.circuit_id
WHERE cp.position <= 5
ORDER BY r.race_name, l.lap_number, d.driver_code;