WITH stint_laps AS (
    SELECT
        d.driver_code,
        d.driver_name,
        t.team_name,
        ts.compound,
        l.lap_time_seconds,
        l.lap_number,
        l.lap_number - ts.start_lap AS stint_lap,
        MIN(l.lap_time_seconds) OVER (
            PARTITION BY sd.session_driver_id
        ) AS best_lap
    FROM tyre_stints ts
    JOIN session_drivers sd
        ON ts.session_driver_id = sd.session_driver_id
    JOIN drivers d
        ON sd.driver_id = d.driver_id
    LEFT JOIN teams t
        ON sd.team_id = t.team_id
    JOIN laps l
        ON l.session_driver_id = ts.session_driver_id
       AND l.lap_number >= ts.start_lap
       AND (ts.end_lap IS NULL OR l.lap_number <= ts.end_lap)
       AND l.is_valid = TRUE
       AND l.lap_time_seconds IS NOT NULL
),
clean AS (
    SELECT *
    FROM stint_laps
    WHERE lap_time_seconds <= best_lap * 1.10
)
SELECT
    RANK() OVER (
        ORDER BY REGR_SLOPE(lap_time_seconds, stint_lap) DESC
    ) AS degradation_rank,
    driver_code,
    driver_name,
    team_name,
    compound,
    COUNT(*) AS laps_in_stint,
    ROUND(
        CAST(REGR_SLOPE(lap_time_seconds, stint_lap) AS NUMERIC), 3
    ) AS seconds_per_lap
FROM clean
GROUP BY driver_code, driver_name, team_name, compound
HAVING COUNT(*) >= 5
ORDER BY degradation_rank
LIMIT 10;