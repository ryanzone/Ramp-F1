-- Variant A: Specific drivers
SELECT l.driver_code, l.lap_number,
       (SELECT ps.position FROM positions ps
        WHERE ps.session_driver_id = l.session_driver_id AND ps.position IS NOT NULL
          AND ps.recorded_at <= l.lap_end_at ORDER BY ps.recorded_at DESC LIMIT 1) AS position
FROM laps l 
WHERE l.driver_code IN (:d0, :d1) 
ORDER BY l.lap_number, l.driver_code;

-- Variant B: Default (top N drivers)
SELECT l.driver_code, l.lap_number,
       (SELECT ps.position FROM positions ps
        WHERE ps.session_driver_id = l.session_driver_id AND ps.position IS NOT NULL
          AND ps.recorded_at <= l.lap_end_at ORDER BY ps.recorded_at DESC LIMIT 1) AS position
FROM laps l 
JOIN current_positions cp ON cp.session_driver_id = l.session_driver_id 
WHERE cp.position <= :top 
ORDER BY l.lap_number, l.driver_code;