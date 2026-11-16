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
),
ranked AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY driver_code ORDER BY lap_number DESC) AS recency 
    FROM clean
)
SELECT RANK() OVER (ORDER BY AVG(lap_time_seconds)) AS pace_rank, driver_code, driver_name, team_name,
       COUNT(*) AS laps_used, ROUND(AVG(lap_time_seconds), 3) AS avg_last_n,
       MIN(lap_time_seconds) AS best_in_window, MAX(lap_number) AS latest_lap
FROM ranked 
WHERE recency <= :n
GROUP BY driver_code, driver_name, team_name
HAVING COUNT(*) >= :min_laps AND MAX(lap_number) >= (SELECT MAX(lap_number) FROM laps) - 3
ORDER BY pace_rank 
LIMIT :limit;