WITH team_stats AS (
    SELECT
        t.team_name,
        COUNT(p.pit_stop_id) AS stops_recorded,
        AVG(p.stop_duration_seconds) AS avg_stop_seconds,
        MIN(p.stop_duration_seconds) AS best_stop_seconds
    FROM pit_stops p
    JOIN session_drivers sd
        ON p.session_driver_id = sd.session_driver_id
    JOIN teams t
        ON sd.team_id = t.team_id
    WHERE p.stop_duration_seconds IS NOT NULL
    GROUP BY t.team_name
    HAVING COUNT(p.pit_stop_id) >= 1
)
SELECT
    RANK() OVER (ORDER BY avg_stop_seconds) AS pit_rank,
    team_name,
    stops_recorded,
    ROUND(avg_stop_seconds, 3) AS avg_stop_seconds,
    ROUND(best_stop_seconds, 3) AS best_stop_seconds
FROM team_stats
ORDER BY pit_rank;