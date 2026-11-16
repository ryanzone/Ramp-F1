SELECT d.driver_code, d.driver_name, d.team_name, c.position, s.compound,
       COALESCE(s.starting_tyre_age, 0) + COALESCE(s.laps_completed, 0) AS tyre_age_laps
FROM drivers d
LEFT JOIN current_stints s ON s.session_driver_id = d.session_driver_id
LEFT JOIN current_positions c ON c.session_driver_id = d.session_driver_id
WHERE NOT EXISTS (SELECT 1 FROM pit_stops p WHERE p.session_driver_id = d.session_driver_id)
  AND COALESCE(s.stint_number, 1) = 1
ORDER BY c.position, d.driver_code;