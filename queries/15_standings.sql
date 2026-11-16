SELECT position, driver_code, driver_name, team_name,
       gap_to_leader_seconds AS gap_to_leader, interval_ahead_seconds AS interval_ahead
FROM current_positions 
WHERE position IS NOT NULL 
ORDER BY position 
LIMIT :limit;