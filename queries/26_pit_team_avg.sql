SELECT RANK() OVER (ORDER BY AVG(stop_duration_seconds)) AS pit_rank, team_name,
       COUNT(*) AS stops_recorded, ROUND(AVG(stop_duration_seconds), 3) AS avg_stop_seconds,
       MIN(stop_duration_seconds) AS best_stop_seconds
FROM pit_stops 
WHERE stop_duration_seconds IS NOT NULL
GROUP BY team_name 
HAVING COUNT(*) >= 1 
ORDER BY pit_rank;