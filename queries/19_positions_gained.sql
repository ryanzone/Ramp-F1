WITH ordered AS (
    SELECT
        p.session_driver_id,
        p.position,
        ROW_NUMBER() OVER (
            PARTITION BY p.session_driver_id
            ORDER BY p.recorded_at ASC
        ) AS rn_first,
        ROW_NUMBER() OVER (
            PARTITION BY p.session_driver_id
            ORDER BY p.recorded_at DESC
        ) AS rn_last
    FROM positions p
    WHERE p.position IS NOT NULL
),
changes AS (
    SELECT
        f.session_driver_id,
        f.position AS first_position,
        l.position AS current_position
    FROM ordered f
    JOIN ordered l
        ON f.session_driver_id = l.session_driver_id
    WHERE f.rn_first = 1
      AND l.rn_last = 1
)
SELECT
    RANK() OVER (
        ORDER BY (c.first_position - c.current_position) DESC
    ) AS change_rank,
    d.driver_code,
    d.driver_name,
    t.team_name,
    c.first_position AS first_recorded_position,
    c.current_position,
    c.first_position - c.current_position AS positions_gained
FROM changes c
JOIN session_drivers sd
    ON c.session_driver_id = sd.session_driver_id
JOIN drivers d
    ON sd.driver_id = d.driver_id
LEFT JOIN teams t
    ON sd.team_id = t.team_id
ORDER BY change_rank, c.current_position
LIMIT 10;