-- "What happened in Week <N> of League <league_id>?" — recap-style extremes.
-- Params: :league_id, :season_year, :week
-- Fact: computed team totals (see CLAUDE.md rule — never mMatchup.totalPoints
-- directly, it lags during a live week).
SELECT
    t.team_name,
    m.display_name AS manager,
    tw.total_points,
    tw.is_final
FROM raw_team_week tw
JOIN teams t ON t.league_id = tw.league_id AND t.season_year = tw.season_year AND t.team_id = tw.team_id
LEFT JOIN managers m ON m.manager_id = t.manager_id
WHERE tw.league_id = :league_id AND tw.season_year = :season_year AND tw.week = :week
ORDER BY tw.total_points DESC;
