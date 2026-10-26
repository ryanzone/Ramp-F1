SELECT
    d.driver_number,
    d.driver_code,
    d.driver_name,
    t.team_name
FROM drivers d
JOIN session_drivers sd ON sd.driver_id = d.driver_id
JOIN teams t ON t.team_id = sd.team_id
ORDER BY d.driver_number;