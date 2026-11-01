
SELECT 'circuits' AS table_name, COUNT(*) AS row_count
FROM circuits

UNION ALL
SELECT 'races', COUNT(*) FROM races

UNION ALL
SELECT 'sessions', COUNT(*) FROM sessions

UNION ALL
SELECT 'teams', COUNT(*) FROM teams

UNION ALL
SELECT 'drivers', COUNT(*) FROM drivers

UNION ALL
SELECT 'session_drivers', COUNT(*) FROM session_drivers

UNION ALL
SELECT 'laps', COUNT(*) FROM laps;
