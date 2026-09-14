-- "What data problems exist right now?" — unresolved issues, most recent first.
-- Params: :league_id (optional — pass NULL to see all leagues)
SELECT detected_at, severity, category, league_id, week, team_id, description
FROM data_issues
WHERE resolved = 0 AND (:league_id IS NULL OR league_id = :league_id)
ORDER BY severity = 'error' DESC, severity = 'warning' DESC, detected_at DESC;
