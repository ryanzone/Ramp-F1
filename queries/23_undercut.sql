WITH cur AS (
    SELECT
        sd.session_driver_id,
        d.driver_code,
        d.driver_name,
        p.position,
        p.interval_ahead_seconds,
        ts.compound,
        COALESCE(ts.starting_tyre_age, 0)
            + COALESCE(ts.end_lap, ts.start_lap) - ts.start_lap AS tyre_age
    FROM positions p
    JOIN session_drivers sd
        ON p.session_driver_id = sd.session_driver_id
    JOIN drivers d
        ON sd.driver_id = d.driver_id
    LEFT JOIN tyre_stints ts
        ON ts.session_driver_id = sd.session_driver_id
       AND p.recorded_at IS NOT NULL
    WHERE p.position IS NOT NULL
)
SELECT
    ch.driver_code AS chaser,
    ah.driver_code AS car_ahead,
    ch.position AS chaser_position,
    ch.interval_ahead_seconds AS gap_to_car_ahead,
    ch.compound AS chaser_tyre,
    ch.tyre_age AS chaser_tyre_age,
    ah.compound AS ahead_tyre,
    ah.tyre_age AS ahead_tyre_age
FROM cur ch
JOIN cur ah
    ON ah.position = ch.position - 1
WHERE ch.interval_ahead_seconds <= 1.0
  AND ch.tyre_age >= 10
  AND ch.tyre_age >= ah.tyre_age
ORDER BY ch.interval_ahead_seconds
LIMIT 10;