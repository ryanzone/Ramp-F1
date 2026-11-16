SELECT recorded_at, lap_number, message 
FROM race_control
WHERE message ILIKE :pen AND message NOT ILIKE :served 
ORDER BY recorded_at;