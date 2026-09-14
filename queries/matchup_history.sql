-- "How have <team A> and <team B> done against each other?" (within one league —
-- cross-league comparison is never meaningful, different scoring rules, CLAUDE.md rule 11)
-- Params: :league_id, :season_year, :team_a, :team_b
SELECT
    m.week,
    m.score_a, m.score_b, m.winner, m.status
FROM raw_matchups m
WHERE m.league_id = :league_id AND m.season_year = :season_year
  AND ((m.team_a = :team_a AND m.team_b = :team_b) OR (m.team_a = :team_b AND m.team_b = :team_a))
ORDER BY m.week;
