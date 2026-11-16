WITH pace AS (
    SELECT
        session_driver_id,
        COUNT(*) AS valid_laps,
        ROUND(AVG(lap_time_seconds), 3) AS avg_lap,
        MIN(lap_time_seconds) AS best_lap
    FROM laps
    WHERE is_valid = TRUE
      AND lap_time_seconds IS NOT NULL
    GROUP BY session_driver_id
),
latest_positions AS (
    SELECT DISTINCT ON (session_driver_id)
        session_driver_id,
        position,
        gap_to_leader_seconds,
        interval_ahead_seconds
    FROM positions
    ORDER BY session_driver_id, recorded_at DESC
)
SELECT
    d.driver_code,
    d.driver_name,
    t.team_name,
    lp.position,
    lp.gap_to_leader_seconds AS gap_to_leader,
    lp.interval_ahead_seconds AS interval_ahead,
    dp.valid_laps,
    dp.avg_lap,
    dp.best_lap,
    ts.compound,
    COALESCE(ts.starting_tyre_age, 0)
        + COALESCE(ts.end_lap, ts.start_lap) - ts.start_lap AS tyre_age,
    ts.stint_number
FROM session_drivers sd
JOIN drivers d ON sd.driver_id = d.driver_id
LEFT JOIN teams t ON sd.team_id = t.team_id
LEFT JOIN latest_positions lp
    ON lp.session_driver_id = sd.session_driver_id
LEFT JOIN pace dp
    ON dp.session_driver_id = sd.session_driver_id
LEFT JOIN tyre_stints ts
    ON ts.session_driver_id = sd.session_driver_id
WHERE d.driver_code = 'VER';