SELECT team_name, driver_code, STRING_AGG(compound, ' > ' ORDER BY stint_number) AS strategy,
       COUNT(*) AS stints, MAX(stint_number) - 1 AS stops_so_far, MAX(start_lap) AS latest_stint_start_lap
FROM tyre_stints 
WHERE team_name ILIKE :t0 -- Optional filter (can add OR team_name ILIKE :t1)
GROUP BY team_name, driver_code 
ORDER BY team_name, driver_code;