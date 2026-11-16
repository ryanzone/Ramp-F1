SELECT driver_code, position, gap_to_leader_seconds AS gap_to_leader, interval_ahead_seconds AS interval_ahead
FROM current_positions 
WHERE driver_code IN (:a, :b) 
ORDER BY position;