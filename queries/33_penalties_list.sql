SELECT
    recorded_at,
    lap_number,
    message
FROM race_control_events
WHERE message ILIKE '%penalty%'
  AND message NOT ILIKE '%served%'
ORDER BY recorded_at;