WITH cur AS (
    SELECT cp.session_driver_id, cp.driver_code, cp.driver_name, cp.position, cp.interval_ahead_seconds,
           st.compound, COALESCE(st.starting_tyre_age, 0) + st.laps_completed AS tyre_age, dp.avg_last5
    FROM current_positions cp
    JOIN current_stints st ON st.session_driver_id = cp.session_driver_id
    LEFT JOIN driver_pace dp ON dp.session_driver_id = cp.session_driver_id
    WHERE cp.position IS NOT NULL
)
SELECT ch.driver_code AS chaser, ah.driver_code AS car_ahead, ch.position AS chaser_position,
       ch.interval_ahead_seconds AS gap_to_car_ahead, ch.compound AS chaser_tyre, ch.tyre_age AS chaser_tyre_age,
       ah.compound AS ahead_tyre, ah.tyre_age AS ahead_tyre_age
FROM cur ch 
JOIN cur ah ON ah.position = ch.position - 1
WHERE ch.interval_ahead_seconds <= :gap AND ch.tyre_age >= :min_age AND ch.tyre_age >= ah.tyre_age
ORDER BY ch.interval_ahead_seconds 
LIMIT :limit;