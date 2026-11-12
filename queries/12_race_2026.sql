SELECT r.season, r.round_number, c.country, s.session_id,
       (SELECT COUNT(*) FROM session_drivers sd WHERE sd.session_id = s.session_id) AS drivers,
       (SELECT COUNT(*) FROM laps l JOIN session_drivers sd USING (session_driver_id)
         WHERE sd.session_id = s.session_id) AS laps,
       (SELECT COUNT(*) FROM pit_stops p JOIN session_drivers sd USING (session_driver_id)
         WHERE sd.session_id = s.session_id) AS pits,
       (SELECT COUNT(*) FROM race_control_events e WHERE e.session_id = s.session_id) AS control,
       (SELECT COUNT(*) FROM weather_samples w WHERE w.session_id = s.session_id) AS weather,
       (SELECT COUNT(*) FROM session_results sr JOIN session_drivers sd USING (session_driver_id)
         WHERE sd.session_id = s.session_id) AS results
FROM races r
JOIN circuits c ON c.circuit_id = r.circuit_id
JOIN sessions s ON s.race_id = r.race_id
WHERE r.season = 2026
ORDER BY r.round_number;