WITH latest_positions AS (
    SELECT DISTINCT ON (session_driver_id)
        session_driver_id,
        position
    FROM positions
    ORDER BY session_driver_id, recorded_at DESC
)
SELECT
    d.driver_code,
    d.driver_name,
    t.team_name,
    lp.position,
    ts.compound,
    ts.starting_tyre_age AS tyre_age_laps
FROM session_drivers sd
JOIN drivers d ON sd.driver_id = d.driver_id
LEFT JOIN teams t ON sd.team_id = t.team_id
LEFT JOIN tyre_stints ts
    ON ts.session_driver_id = sd.session_driver_id
   AND ts.stint_number = 1
LEFT JOIN latest_positions lp
    ON lp.session_driver_id = sd.session_driver_id
WHERE NOT EXISTS (
    SELECT 1
    FROM pit_stops p
    WHERE p.session_driver_id = sd.session_driver_id
)
ORDER BY lp.position NULLS LAST, d.driver_code;