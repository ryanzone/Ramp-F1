WITH base AS (
    SELECT
        d.driver_code,
        d.driver_name,
        t.team_name,
        l.lap_number,
        l.lap_time_seconds
    FROM laps l
    JOIN session_drivers sd
        ON l.session_driver_id = sd.session_driver_id
    JOIN drivers d
        ON sd.driver_id = d.driver_id
    LEFT JOIN teams t
        ON sd.team_id = t.team_id
    WHERE l.is_valid = TRUE
      AND l.lap_time_seconds IS NOT NULL
),
clean AS (
    SELECT *
    FROM (
        SELECT b.*,
            MIN(lap_time_seconds) OVER (
                PARTITION BY driver_code
            ) AS best
        FROM base b
    ) x
    WHERE lap_time_seconds <= best * 1.10
)
SELECT
    RANK() OVER (ORDER BY AVG(lap_time_seconds)) AS pace_rank,
    driver_code,
    driver_name,
    team_name,
    COUNT(*) AS laps_used,
    ROUND(AVG(lap_time_seconds), 3) AS avg_lap,
    MIN(lap_time_seconds) AS best_lap
FROM clean
GROUP BY driver_code, driver_name, team_name
HAVING COUNT(*) >= 5
ORDER BY pace_rank
