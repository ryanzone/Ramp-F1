SELECT driver_code, team_name, stint_number, compound, start_lap,
       COALESCE(end_lap, start_lap + laps_completed - 1) AS last_lap,
       CASE WHEN end_lap IS NULL THEN 'running' ELSE 'finished' END AS status, laps_completed
FROM tyre_stints 
ORDER BY team_name, driver_code, stint_number;