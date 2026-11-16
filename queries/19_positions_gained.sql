WITH ordered AS (
    SELECT session_driver_id, position, ROW_NUMBER() OVER (PARTITION BY session_driver_id ORDER BY recorded_at) AS rn
    FROM positions 
    WHERE position IS NOT NULL
)
SELECT RANK() OVER (ORDER BY (o.position - c.position) DESC) AS change_rank, c.driver_code, c.driver_name,
       c.team_name, o.position AS first_recorded_position, c.position AS current_position,
       o.position - c.position AS positions_gained
FROM ordered o 
JOIN current_positions c ON c.session_driver_id = o.session_driver_id
WHERE o.rn = 1 AND c.position IS NOT NULL
ORDER BY change_rank, c.position 
LIMIT :limit;
-- Note: Change DESC to ASC for positions lost