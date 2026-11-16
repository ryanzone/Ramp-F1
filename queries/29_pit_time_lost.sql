SELECT team_name, driver_code, COUNT(*) AS stops, ROUND(SUM(lane_duration_seconds), 3) AS pit_lane_seconds,
       ROUND(SUM(stop_duration_seconds), 3) AS stationary_seconds,
       ROUND(AVG(lane_duration_seconds), 3) AS avg_lane_seconds
FROM pit_stops 
GROUP BY team_name, driver_code
ORDER BY pit_lane_seconds DESC NULLS LAST 
LIMIT :limit;