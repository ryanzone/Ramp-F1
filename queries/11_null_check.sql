SELECT d.driver_code, sr.final_position, sr.number_of_laps,
       sr.dnf, sr.dns, sr.dsq
FROM session_results sr
JOIN session_drivers sd ON sd.session_driver_id = sr.session_driver_id
JOIN drivers d ON d.driver_id = sd.driver_id
WHERE sd.session_id = 2
ORDER BY sr.final_position NULLS LAST;