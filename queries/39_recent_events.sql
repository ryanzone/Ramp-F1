SELECT rc.recorded_at AS event_time, 'race control' AS kind, rc.message AS detail
FROM race_control rc 
JOIN session_info si ON TRUE
WHERE rc.recorded_at >= si.replay_time - (:minutes * INTERVAL '1 minute')
UNION ALL
SELECT p.pit_exit_at, 'pit stop', p.driver_code || ' left the pits (lap ' || p.lap_number || ')'
FROM pit_stops p 
JOIN session_info si ON TRUE
WHERE p.pit_exit_at >= si.replay_time - (:minutes * INTERVAL '1 minute')
ORDER BY event_time DESC 
LIMIT :limit;