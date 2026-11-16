SELECT d.driver_code, d.driver_name, d.team_name, COUNT(p.stop_number) AS recorded_stops,
       COALESCE(MAX(s.stint_number), 1) - 1 AS stops_from_tyre_stints
FROM drivers d
LEFT JOIN pit_stops p ON p.session_driver_id = d.session_driver_id
LEFT JOIN current_stints s ON s.session_driver_id = d.session_driver_id
GROUP BY d.driver_code, d.driver_name, d.team_name
ORDER BY stops_from_tyre_stints DESC, recorded_stops DESC, d.driver_code;