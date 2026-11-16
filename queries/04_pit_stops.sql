SELECT
    d.driver_number,
    d.driver_code,
    p.lap_number,
    p.stop_number,
    p.pit_timestamp,
    p.lane_duration_seconds,
    p.stop_duration_seconds,
    p.pit_timestamp
        + COALESCE(p.lane_duration_seconds, 0)
          * INTERVAL '1 second' AS pit_exit_time
FROM pit_stops p
JOIN session_drivers sd
    ON sd.session_driver_id = p.session_driver_id
JOIN drivers d
    ON d.driver_id = sd.driver_id
WHERE sd.session_id = 1
  AND p.pit_timestamp IS NOT NULL
ORDER BY p.pit_timestamp;