SELECT
    r.season,
    r.race_name,
    c.circuit_name,
    s.session_type,
    s.session_date,
    s.status
FROM sessions s
JOIN races r ON r.race_id = s.race_id
JOIN circuits c ON c.circuit_id = r.circuit_id
ORDER BY s.session_date;