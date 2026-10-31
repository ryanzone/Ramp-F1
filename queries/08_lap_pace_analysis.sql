-- =========================================================
-- RAMP: LAP PACE AND SECTOR ANALYSIS
-- Calculates recent pace and rolling performance baselines
-- =========================================================

CREATE OR REPLACE VIEW v_lap_pace_analysis AS

WITH lap_metrics AS (
    SELECT
        sd.session_id,
        l.session_driver_id,
        d.driver_code,
        d.driver_name,
        l.lap_number,
        l.lap_time_seconds,
        l.sector1_seconds,
        l.sector2_seconds,
        l.sector3_seconds,
        l.speed_trap_kmh,

        AVG(l.lap_time_seconds) OVER (
            PARTITION BY l.session_driver_id
            ORDER BY l.lap_number
            ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING
        ) AS baseline_lap_time,

        AVG(l.sector1_seconds) OVER (
            PARTITION BY l.session_driver_id
            ORDER BY l.lap_number
            ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING
        ) AS baseline_sector1,

        AVG(l.sector2_seconds) OVER (
            PARTITION BY l.session_driver_id
            ORDER BY l.lap_number
            ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING
        ) AS baseline_sector2,

        AVG(l.sector3_seconds) OVER (
            PARTITION BY l.session_driver_id
            ORDER BY l.lap_number
            ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING
        ) AS baseline_sector3,

        COUNT(l.lap_time_seconds) OVER (
            PARTITION BY l.session_driver_id
            ORDER BY l.lap_number
            ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING
        ) AS baseline_lap_count

    FROM laps l
    JOIN session_drivers sd
        ON sd.session_driver_id = l.session_driver_id
    JOIN drivers d
        ON d.driver_id = sd.driver_id

    WHERE l.is_valid = TRUE
)

SELECT
    session_id,
    session_driver_id,
    driver_code,
    driver_name,
    lap_number,

    lap_time_seconds,
    sector1_seconds,
    sector2_seconds,
    sector3_seconds,
    speed_trap_kmh,

    baseline_lap_time,
    baseline_sector1,
    baseline_sector2,
    baseline_sector3,

    baseline_lap_count,

    ROUND(
        (lap_time_seconds - baseline_lap_time)::NUMERIC,
        3
    ) AS lap_time_difference,

    ROUND(
        (sector1_seconds - baseline_sector1)::NUMERIC,
        3
    ) AS sector1_difference,

    ROUND(
        (sector2_seconds - baseline_sector2)::NUMERIC,
        3
    ) AS sector2_difference,

    ROUND(
        (sector3_seconds - baseline_sector3)::NUMERIC,
        3
    ) AS sector3_difference

FROM lap_metrics;


-- Display lap pace analysis
SELECT *
FROM v_lap_pace_analysis
ORDER BY driver_code, lap_number;