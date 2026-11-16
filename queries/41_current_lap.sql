SELECT MAX(lap_number) AS latest_completed_lap, COUNT(DISTINCT driver_code) AS drivers_with_laps,
       MIN(lap_end_at) AS first_lap_finished_at, MAX(lap_end_at) AS latest_lap_finished_at 
FROM laps;