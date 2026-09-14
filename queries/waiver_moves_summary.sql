-- "How has <team>'s waiver activity paid off?" — outcome-based, since neither
-- league uses FAAB (CLAUDE.md rule 9), there's no bid budget to evaluate.
-- Params: :league_id, :season_year, :team_id
SELECT
    pa.full_name AS added,
    pd.full_name AS dropped,
    dw.points_added_over_horizon,
    dw.points_dropped_over_horizon,
    dw.net_value,
    dw.horizon_weeks,
    dw.is_complete
FROM derived_waiver_moves dw
JOIN raw_transactions t ON t.transaction_id = dw.transaction_id
JOIN players pa ON pa.player_id = dw.player_added
LEFT JOIN players pd ON pd.player_id = dw.player_dropped
WHERE t.league_id = :league_id AND t.season_year = :season_year AND t.team_id = :team_id
ORDER BY t.week DESC;
