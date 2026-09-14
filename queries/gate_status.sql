-- "Are luck/power-ranking metrics unlocked yet for <team>?"
-- Params: :league_id, :season_year, :team_id, :through_week
SELECT
    weeks_played,
    is_provisional,
    CASE WHEN weeks_played >= 5 THEN 'unlocked' ELSE 'withheld — need ' || (5 - weeks_played) || ' more weeks' END AS luck_power_gate,
    CASE WHEN weeks_played >= 7 THEN 'unlocked' ELSE 'withheld — need ' || (7 - weeks_played) || ' more weeks' END AS playoff_odds_gate
FROM derived_team_season
WHERE league_id = :league_id AND season_year = :season_year AND team_id = :team_id AND through_week = :through_week;
