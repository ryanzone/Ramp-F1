SELECT
    recorded_at,
    lap_number,
    category,
    flag,
    scope,
    message
FROM race_control_events
WHERE category IN ('Flag', 'SafetyCar', 'SessionStatus')
ORDER BY recorded_at DESC
LIMIT 10;