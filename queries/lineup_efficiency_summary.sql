-- "How efficient has everyone's lineup-setting been in League <league_id>?"
-- Params: :league_id, :season_year, :through_week
-- Computed: season_lineup_efficiency = actual / optimal, averaged across weeks played.
SELECT
    t.team_name,
    m.display_name AS manager,
    ds.weeks_played,
    ROUND(ds.season_lineup_efficiency * 100, 1) AS lineup_efficiency_pct,
    ds.total_bench_points,
    ds.is_provisional
FROM derived_team_season ds
JOIN teams t ON t.league_id = ds.league_id AND t.season_year = ds.season_year AND t.team_id = ds.team_id
LEFT JOIN managers m ON m.manager_id = t.manager_id
WHERE ds.league_id = :league_id AND ds.season_year = :season_year AND ds.through_week = :through_week
ORDER BY ds.season_lineup_efficiency DESC;
