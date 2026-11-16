SELECT
    d.driver_number,
    d.driver_code,
    d.driver_name,
    t.team_name
FROM session_drivers sd
JOIN drivers d ON d.driver_id = sd.driver_id
LEFT JOIN teams t ON t.team_id = sd.team_id
WHERE sd.session_id = 1
ORDER BY d.driver_number;