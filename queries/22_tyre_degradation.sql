WITH stint_laps AS (
    SELECT s.driver_code, s.driver_name, s.team_name, s.compound, l.lap_time_seconds, l.lap_number, l.lap_number - s.start_lap AS stint_lap
    FROM current_stints s
    JOIN laps l ON l.session_driver_id = s.session_driver_id AND l.lap_number >= s.start_lap
               AND l.is_valid AND l.lap_time_seconds IS NOT NULL
    JOIN driver_pace p ON p.session_driver_id = s.session_driver_id
    WHERE l.lap_time_seconds <= p.best_lap * :clean_factor
)
SELECT RANK() OVER (ORDER BY REGR_SLOPE(lap_time_seconds, stint_lap) DESC) AS degradation_rank, driver_code,
       driver_name, team_name, compound, COUNT(*) AS laps_in_stint,
       ROUND(CAST(REGR_SLOPE(lap_time_seconds, stint_lap) AS NUMERIC), 3) AS seconds_per_lap
FROM stint_laps 
GROUP BY driver_code, driver_name, team_name, compound
HAVING COUNT(*) >= :min_laps AND MAX(lap_number) >= (SELECT MAX(lap_number) FROM laps) - 3
ORDER BY degradation_rank 
LIMIT :limit;