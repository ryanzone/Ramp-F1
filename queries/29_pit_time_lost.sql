SELECT
    t.team_name,
    d.driver_code,
    COUNT(p.pit_stop_id) AS stops,
    ROUND(SUM(p.lane_duration_seconds), 3) AS pit_lane_seconds,
    ROUND(SUM(p.stop_duration_seconds), 3) AS stationary_seconds,
    ROUND(AVG(p.lane_duration_seconds), 3) AS avg_lane_seconds
FROM pit_stops p
JOIN session_drivers sd
    ON p.session_driver_id = sd.session_driver_id
JOIN drivers d
    ON sd.driver_id = d.driver_id
LEFT JOIN teams t
    ON sd.team_id = t.team_id
GROUP BY t.team_name, d.driver_code
ORDER BY pit_lane_seconds DESC NULLS LAST
LIMIT 10;