SELECT
    recorded_at,
    air_temperature,
    track_temperature,
    humidity,
    rainfall,
    wind_speed
FROM weather_samples
ORDER BY recorded_at DESC
LIMIT 1;