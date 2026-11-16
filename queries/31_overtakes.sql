WITH cur AS (
    SELECT cp.session_driver_id, cp.driver_code, cp.driver_name, cp.position, cp.interval_ahead_seconds,
           st.compound, COALESCE(st.starting_tyre_age, 0) + st.laps_completed AS tyre_age, dp.avg_last5
    FROM current_positions cp
    JOIN current_stints st ON st.session_driver_id = cp.session_driver_id
    LEFT JOIN driver_pace dp ON dp.session_driver_id = cp.session_driver_id
    WHERE cp.position IS NOT NULL
)
SELECT ch.driver_code AS chaser, ah.driver_code AS car_ahead, ch.position AS attacker_position,
       ch.interval_ahead_seconds AS gap_seconds, ch.avg_last5 AS attacker_pace_last5, ah.avg_last5 AS ahead_pace_last5,
       ROUND(ah.avg_last5 - ch.avg_last5, 3) AS pace_advantage_seconds
FROM cur ch 
JOIN cur ah ON ah.position = ch.position - 1
WHERE ch.interval_ahead_seconds <= :gap AND ah.avg_last5 - ch.avg_last5 >= :min_adv
ORDER BY ch.interval_ahead_seconds 
LIMIT :limit;