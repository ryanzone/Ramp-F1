SELECT
    t.team_name,
    COUNT(DISTINCT d.driver_code) AS cars_entered,
    MIN(r.final_position) AS best_finish,
    SUM(r.grid_position - r.final_position) AS net_positions_gained
FROM teams t
JOIN session_drivers sd
    ON t.team_id = sd.team_id
JOIN drivers d
    ON sd.driver_id = d.driver_id
LEFT JOIN session_results r
    ON sd.session_driver_id = r.session_driver_id
GROUP BY t.team_name
ORDER BY best_finish ASC NULLS LAST;