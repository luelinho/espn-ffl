-- "Who was leading League <league_id> after Week <N>?"
-- Params: :league_id, :season_year, :week
-- Fact: ESPN's own reported record/points, snapshotted (not reconstructed).
SELECT
    t.team_name,
    m.display_name AS manager,
    s.wins, s.losses, s.ties,
    s.points_for, s.points_against,
    s.playoff_seed
FROM standings_snapshots s
JOIN teams t ON t.league_id = s.league_id AND t.season_year = s.season_year AND t.team_id = s.team_id
LEFT JOIN managers m ON m.manager_id = t.manager_id
WHERE s.league_id = :league_id AND s.season_year = :season_year AND s.week = :week
ORDER BY s.wins DESC, s.points_for DESC;
