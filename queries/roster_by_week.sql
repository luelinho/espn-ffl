-- "What was <team>'s roster in Week <N> of League <league_id>?"
-- Params: :league_id, :season_year, :team_id, :week
-- Fact: stored roster entries, each player's real per-league points already
-- applied by ESPN (see CLAUDE.md rule 1 — league-scoped points, not universal).
SELECT
    p.full_name,
    p.default_position_id,
    CASE WHEN r.is_starter THEN 'Starter' ELSE 'Bench/IR' END AS status,
    r.lineup_slot_id,
    r.points_scored,
    r.is_final
FROM raw_roster_entries r
JOIN players p ON p.player_id = r.player_id
WHERE r.league_id = :league_id AND r.season_year = :season_year
  AND r.team_id = :team_id AND r.week = :week
ORDER BY r.is_starter DESC, r.points_scored DESC;
