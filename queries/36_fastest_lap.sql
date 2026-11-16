SELECT RANK() OVER (ORDER BY lap_time_seconds) AS lap_rank, driver_code, driver_name, team_name,
       lap_number, lap_time_seconds
FROM laps 
WHERE is_valid AND lap_time_seconds IS NOT NULL
ORDER BY lap_time_seconds 
LIMIT :limit;