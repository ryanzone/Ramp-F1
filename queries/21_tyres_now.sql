SELECT s.driver_code, s.driver_name, s.team_name, s.compound, s.stint_number, s.start_lap,
       COALESCE(s.starting_tyre_age, 0) + s.laps_completed AS tyre_age_laps, c.position
FROM current_stints s 
LEFT JOIN current_positions c ON c.session_driver_id = s.session_driver_id
WHERE UPPER(s.compound) = :compound -- Optional filter
ORDER BY s.compound, c.position;