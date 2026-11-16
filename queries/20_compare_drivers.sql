WITH a AS (
    SELECT lap_number, lap_time_seconds FROM laps
    WHERE driver_code = :a AND is_valid AND lap_time_seconds IS NOT NULL
),
b AS (
    SELECT lap_number, lap_time_seconds FROM laps
    WHERE driver_code = :b AND is_valid AND lap_time_seconds IS NOT NULL
)
SELECT COALESCE(a.lap_number, b.lap_number) AS lap_number, a.lap_time_seconds AS a_time,
       b.lap_time_seconds AS b_time, ROUND(a.lap_time_seconds - b.lap_time_seconds, 3) AS delta_a_minus_b
FROM a 
FULL JOIN b ON a.lap_number = b.lap_number 
ORDER BY lap_number;