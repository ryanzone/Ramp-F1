SELECT
    recorded_at,
    air_temperature,
    track_temperature,
    humidity,
    rainfall,
    wind_speed
FROM weather_samples
WHERE session_id = 1
  AND recorded_at IS NOT NULL
ORDER BY recorded_at;