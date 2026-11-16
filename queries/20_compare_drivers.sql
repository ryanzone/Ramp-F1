WITH a AS (
    SELECT l.lap_number, l.lap_time_seconds
    FROM laps l
    JOIN session_drivers sd ON l.session_driver_id = sd.session_driver_id
    JOIN drivers d ON sd.driver_id = d.driver_id
    WHERE d.driver_code = 'VER'
      AND l.is_valid = TRUE
      AND l.lap_time_seconds IS NOT NULL
),
b AS (
    SELECT l.lap_number, l.lap_time_seconds
    FROM laps l
    JOIN session_drivers sd ON l.session_driver_id = sd.session_driver_id
    JOIN drivers d ON sd.driver_id = d.driver_id
    WHERE d.driver_code = 'HAM'
      AND l.is_valid = TRUE
      AND l.lap_time_seconds IS NOT NULL
)
SELECT
    COALESCE(a.lap_number, b.lap_number) AS lap_number,
    a.lap_time_seconds AS a_time,
    b.lap_time_seconds AS b_time,
    ROUND(a.lap_time_seconds - b.lap_time_seconds, 3) AS delta_a_minus_b
FROM a
FULL JOIN b ON a.lap_number = b.lap_number
ORDER BY lap_number;