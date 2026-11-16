SELECT
    recorded_at,
    lap_number,
    CASE
        WHEN message ILIKE '%penalty served%' THEN 'penalty served'
        WHEN message ILIKE '%penalty for%' THEN 'penalty'
        WHEN message ILIKE '%no further%' THEN 'no further action'
        WHEN message ILIKE '%investigat%' THEN 'investigation'
        WHEN message ILIKE '%deleted%' THEN 'lap time deleted'
        WHEN message ILIKE '%noted%' THEN 'noted'
        ELSE 'other'
    END AS ruling,
    message
FROM race_control_events
WHERE (
    message ILIKE '%VER%'
    OR message ILIKE '%CAR 1%'
)
AND (
    message ILIKE '%penalty%'
    OR message ILIKE '%investigat%'
    OR message ILIKE '%incident%'
    OR message ILIKE '%deleted%'
    OR message ILIKE '%noted%'
    OR message ILIKE '%reprimand%'
    OR message ILIKE '%no further%'
    OR flag = 'BLACK AND WHITE'
)
ORDER BY recorded_at;