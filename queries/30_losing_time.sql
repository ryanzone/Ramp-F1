WITH v AS (
    SELECT
        d.driver_code,
        d.driver_name,
        t.team_name,
        l.session_driver_id,
        l.lap_number,
        l.lap_time_seconds,
        AVG(l.lap_time_seconds) OVER (
            PARTITION BY l.session_driver_id
            ORDER BY l.lap_number
            ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING
        ) AS baseline,
        COUNT(l.lap_time_seconds) OVER (
            PARTITION BY l.session_driver_id
            ORDER BY l.lap_number
            ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING
        ) AS baseline_laps
    FROM laps l
    JOIN session_drivers sd
        ON l.session_driver_id = sd.session_driver_id
    JOIN drivers d
        ON sd.driver_id = d.driver_id
    LEFT JOIN teams t
        ON sd.team_id = t.team_id
    WHERE l.is_valid = TRUE
      AND l.lap_time_seconds IS NOT NULL
)
SELECT
    driver_code,
    driver_name,
    team_name,
    lap_number,
    lap_time_seconds,
    ROUND(baseline, 3) AS baseline,
    ROUND(lap_time_seconds - baseline, 3) AS time_lost_vs_baseline
FROM v
WHERE lap_number > (
    SELECT MAX(lap_number) FROM laps
) - 5
  AND baseline_laps >= 3
  AND lap_time_seconds - baseline >= 1.0
ORDER BY time_lost_vs_baseline DESC
LIMIT 10;