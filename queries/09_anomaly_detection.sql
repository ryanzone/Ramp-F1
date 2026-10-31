-- =========================================================
-- RAMP: ANOMALY DETECTION
-- Detects unusual lap pace and long pit stops
-- Stores detected events in detected_events
-- =========================================================


-- STEP 1: DETECT UNUSUAL LAP PACE

WITH pace_anomalies AS (

    SELECT
        session_driver_id,
        lap_number,
        driver_code,
        lap_time_seconds,
        baseline_lap_time,

        lap_time_difference,

        CASE
            WHEN lap_time_difference >= 3.0
                THEN 'HIGH'

            WHEN lap_time_difference >= 1.5
                THEN 'MEDIUM'

            ELSE 'LOW'
        END AS severity

    FROM v_lap_pace_analysis

    WHERE baseline_lap_count >= 3
      AND baseline_lap_time IS NOT NULL
      AND lap_time_difference >= 1.5
)

INSERT INTO detected_events (
    session_driver_id,
    lap_number,
    event_type,
    severity,
    trigger_metric,
    observed_value,
    baseline_value,
    deviation,
    description
)

SELECT
    p.session_driver_id,
    p.lap_number,
    'PACE_DROP',
    p.severity,
    'lap_time_seconds',
    p.lap_time_seconds,
    p.baseline_lap_time,
    p.lap_time_difference,

    CONCAT(
        'Unusual pace drop detected for ',
        p.driver_code,
        '. Lap time increased by ',
        ROUND(p.lap_time_difference, 2),
        ' seconds compared with the recent rolling baseline.'
    )

FROM pace_anomalies p

WHERE NOT EXISTS (
    SELECT 1
    FROM detected_events e
    WHERE e.session_driver_id = p.session_driver_id
      AND e.lap_number = p.lap_number
      AND e.event_type = 'PACE_DROP'
);


-- STEP 2: DETECT UNUSUALLY LONG PIT STOPS

WITH pit_baselines AS (

    SELECT
        p.pit_stop_id,
        p.session_driver_id,
        p.lap_number,
        p.stop_duration_seconds,

        AVG(p.stop_duration_seconds) OVER (
            PARTITION BY p.session_driver_id
            ORDER BY p.stop_number
            ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING
        ) AS baseline_stop_duration,

        COUNT(p.stop_duration_seconds) OVER (
            PARTITION BY p.session_driver_id
            ORDER BY p.stop_number
            ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING
        ) AS baseline_stop_count

    FROM pit_stops p

    WHERE p.stop_duration_seconds IS NOT NULL
),

pit_anomalies AS (

    SELECT
        session_driver_id,
        lap_number,
        stop_duration_seconds,
        baseline_stop_duration,

        stop_duration_seconds - baseline_stop_duration
            AS deviation,

        CASE
            WHEN stop_duration_seconds >=
                 baseline_stop_duration * 2
                THEN 'HIGH'

            ELSE 'MEDIUM'
        END AS severity

    FROM pit_baselines

    WHERE baseline_stop_count >= 1
      AND baseline_stop_duration > 0
      AND stop_duration_seconds >=
          GREATEST(
              baseline_stop_duration * 1.5,
              baseline_stop_duration + 2.0
          )
)

INSERT INTO detected_events (
    session_driver_id,
    lap_number,
    event_type,
    severity,
    trigger_metric,
    observed_value,
    baseline_value,
    deviation,
    description
)

SELECT
    p.session_driver_id,
    p.lap_number,
    'LONG_PIT_STOP',
    p.severity,
    'stop_duration_seconds',
    p.stop_duration_seconds,
    p.baseline_stop_duration,
    p.deviation,

    CONCAT(
        'Unusually long pit stop detected. Duration: ',
        ROUND(p.stop_duration_seconds, 2),
        ' seconds. Previous stop average: ',
        ROUND(p.baseline_stop_duration, 2),
        ' seconds.'
    )

FROM pit_anomalies p

WHERE NOT EXISTS (
    SELECT 1
    FROM detected_events e
    WHERE e.session_driver_id = p.session_driver_id
      AND e.lap_number IS NOT DISTINCT FROM p.lap_number
      AND e.event_type = 'LONG_PIT_STOP'
);


-- STEP 3: DISPLAY DETECTED EVENTS

SELECT
    e.event_id,
    d.driver_code,
    e.lap_number,
    e.event_type,
    e.severity,
    e.trigger_metric,
    e.observed_value,
    e.baseline_value,
    e.deviation,
    e.description,
    e.detected_at

FROM detected_events e

JOIN session_drivers sd
    ON sd.session_driver_id = e.session_driver_id

JOIN drivers d
    ON d.driver_id = sd.driver_id

ORDER BY e.detected_at DESC;