SELECT cp.driver_code, cp.driver_name, cp.team_name, cp.position, cp.gap_to_leader_seconds AS gap_to_leader,
       cp.interval_ahead_seconds AS interval_ahead, dp.valid_laps, dp.avg_lap, dp.best_lap, dp.avg_last5,
       st.compound, COALESCE(st.starting_tyre_age, 0) + st.laps_completed AS tyre_age, st.stint_number
FROM current_positions cp
LEFT JOIN driver_pace dp ON dp.session_driver_id = cp.session_driver_id
LEFT JOIN current_stints st ON st.session_driver_id = cp.session_driver_id
WHERE cp.driver_code = :driver;