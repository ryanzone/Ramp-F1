WITH v AS (
    SELECT driver_code, driver_name, team_name, lap_number, lap_time_seconds,
           AVG(lap_time_seconds) OVER (PARTITION BY driver_code ORDER BY lap_number
                ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING) AS baseline,
           COUNT(lap_time_seconds) OVER (PARTITION BY driver_code ORDER BY lap_number
                ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING) AS baseline_laps
    FROM laps 
    WHERE is_valid AND lap_time_seconds IS NOT NULL
)
SELECT driver_code, driver_name, team_name, lap_number, lap_time_seconds, ROUND(baseline, 3) AS baseline,
       ROUND(lap_time_seconds - baseline, 3) AS time_lost_vs_baseline
FROM v 
WHERE lap_number > (SELECT MAX(lap_number) FROM laps) - :n 
  AND baseline_laps >= 3
  AND lap_time_seconds - baseline >= :threshold
ORDER BY time_lost_vs_baseline DESC 
LIMIT :limit;