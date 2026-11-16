SELECT
    s.session_id,
    r.season,
    r.round_number,
    r.race_name,
    c.circuit_name,
    c.country,
    r.race_date,
    (
        SELECT MAX(l.lap_number)
        FROM laps l
        JOIN session_drivers sd USING (session_driver_id)
        WHERE sd.session_id = s.session_id
    ) AS total_laps,
    EXISTS (
        SELECT 1
        FROM laps l
        JOIN session_drivers sd USING (session_driver_id)
        WHERE sd.session_id = s.session_id
          AND l.lap_start_at IS NOT NULL
    ) AS replay_ready
FROM sessions s
JOIN races r ON r.race_id = s.race_id
JOIN circuits c ON c.circuit_id = r.circuit_id
WHERE s.session_type = 'Race'
ORDER BY r.season DESC, r.round_number;