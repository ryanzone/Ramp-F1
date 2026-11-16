WITH base AS (
    SELECT driver_code, driver_name, team_name, lap_number, lap_time_seconds
    FROM laps 
    WHERE is_valid AND lap_time_seconds IS NOT NULL
),
clean AS (
    SELECT * FROM (
        SELECT b.*, MIN(lap_time_seconds) OVER (PARTITION BY driver_code) AS best 
        FROM base b
    ) x
    WHERE lap_time_seconds <= best * :clean_factor
)
SELECT RANK() OVER (ORDER BY AVG(lap_time_seconds)) AS pace_rank, driver_code, driver_name, team_name,
       COUNT(*) AS laps_used, ROUND(AVG(lap_time_seconds), 3) AS avg_lap, MIN(lap_time_seconds) AS best_lap
FROM clean 
GROUP BY driver_code, driver_name, team_name
HAVING COUNT(*) >= :min_laps AND COUNT(*) >= 0.5 * (SELECT MAX(lap_number) FROM laps)
ORDER BY pace_rank 
LIMIT :limit;