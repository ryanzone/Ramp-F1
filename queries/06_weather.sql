SELECT
    s.session_type,
    w.recorded_at,
    w.air_temperature,
    w.track_temperature,
    w.humidity,
    w.rainfall,
    w.wind_speed
FROM weather_samples w
JOIN sessions s ON s.session_id = w.session_id
ORDER BY w.recorded_at;