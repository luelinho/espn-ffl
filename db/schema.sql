-- ESPN Fantasy Football — multi-league schema. See SPEC.md §3 for design
-- rationale. SQLite, Postgres-shaped: integer surrogate/natural keys,
-- foreign keys enforced, no SQLite-only types.

PRAGMA foreign_keys = ON;

-- === Reference ==============================================================

CREATE TABLE IF NOT EXISTS leagues (
  league_id       INTEGER PRIMARY KEY,     -- ESPN's own numeric league ID
  name            TEXT NOT NULL,
  my_team_hint    TEXT
);

CREATE TABLE IF NOT EXISTS league_seasons (
  league_id                  INTEGER NOT NULL REFERENCES leagues(league_id),
  season_year                INTEGER NOT NULL,
  team_count                 INTEGER NOT NULL,
  scoring_type                TEXT NOT NULL,
  waiver_type                 TEXT NOT NULL,
  regular_season_weeks        INTEGER NOT NULL,
  final_week                  INTEGER NOT NULL,
  playoff_team_count          INTEGER,
  playoff_seeding_rule        TEXT,
  trade_veto_votes_required   INTEGER,
  roster_slot_counts_json     TEXT NOT NULL,
  scoring_items_json          TEXT NOT NULL,
  config_json                 TEXT,
  last_verified                TIMESTAMP,
  PRIMARY KEY (league_id, season_year)
);

CREATE TABLE IF NOT EXISTS pro_teams (
  pro_team_id   INTEGER NOT NULL,
  season_year   INTEGER NOT NULL,
  name          TEXT NOT NULL,
  abbrev        TEXT NOT NULL,
  PRIMARY KEY (pro_team_id, season_year)
);

CREATE TABLE IF NOT EXISTS players (
  player_id           INTEGER PRIMARY KEY,   -- ESPN's global player ID
  full_name           TEXT NOT NULL,
  default_position_id INTEGER NOT NULL,      -- 1 QB | 2 RB | 3 WR | 4 TE | 5 K | 16 D/ST (confirmed Phase 1)
  eligible_slots_json TEXT,                  -- raw eligibleSlots array — real data shows this is
                                              -- broader than a naive position->slot mapping (e.g. a
                                              -- WR's eligibleSlots includes slot 3, not just 4/23),
                                              -- so lineup optimization uses this, never a hand-guessed map
  pro_team_id          INTEGER
);

CREATE TABLE IF NOT EXISTS raw_player_snapshots (
  player_id      INTEGER NOT NULL,
  snapshot_date  DATE NOT NULL,
  ownership_pct  REAL,
  injury_status  TEXT,
  fetched_at     TIMESTAMP NOT NULL,
  PRIMARY KEY (player_id, snapshot_date)
);

-- Real-world NFL game status, universal (not league-scoped) — confirmed
-- live in ESPN's proTeamSchedules response (2026-09-14): each game carries
-- inProgress and detail ('Final' once done), which is exactly what's
-- needed to tell "hasn't played" from "playing right now" from "done" —
-- something points_scored alone can't distinguish (null vs. a real number
-- doesn't say whether that number is still changing).
CREATE TABLE IF NOT EXISTS raw_pro_games (
  season_year       INTEGER NOT NULL,
  week              INTEGER NOT NULL,
  game_id           INTEGER NOT NULL,
  home_team_id      INTEGER NOT NULL,
  away_team_id      INTEGER NOT NULL,
  home_score        INTEGER,
  away_score        INTEGER,
  detail            TEXT,
  in_progress       BOOLEAN NOT NULL DEFAULT 0,
  percent_complete  REAL,
  kickoff_utc       TIMESTAMP,
  fetched_at        TIMESTAMP NOT NULL,
  PRIMARY KEY (season_year, week, game_id)
);

-- === Managers and teams ======================================================

CREATE TABLE IF NOT EXISTS managers (
  manager_id     INTEGER PRIMARY KEY AUTOINCREMENT,
  espn_member_id TEXT NOT NULL UNIQUE,       -- SWID/GUID, e.g. '{E1AB20C5-...}'
  display_name   TEXT,
  is_owner       BOOLEAN NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS teams (
  league_id     INTEGER NOT NULL,
  season_year   INTEGER NOT NULL,
  team_id       INTEGER NOT NULL,
  manager_id    INTEGER REFERENCES managers(manager_id),
  team_name     TEXT NOT NULL,
  division_id   INTEGER,
  PRIMARY KEY (league_id, season_year, team_id),
  FOREIGN KEY (league_id, season_year) REFERENCES league_seasons(league_id, season_year)
);

-- === Raw weekly facts ========================================================

CREATE TABLE IF NOT EXISTS raw_player_week_stats (
  season_year   INTEGER NOT NULL,
  week          INTEGER NOT NULL,
  player_id     INTEGER NOT NULL,
  stats_json    TEXT NOT NULL,
  is_final      BOOLEAN NOT NULL DEFAULT 0,
  source        TEXT NOT NULL,
  fetched_at    TIMESTAMP NOT NULL,
  PRIMARY KEY (season_year, week, player_id)
);

CREATE TABLE IF NOT EXISTS raw_roster_entries (
  league_id       INTEGER NOT NULL,
  season_year     INTEGER NOT NULL,
  week            INTEGER NOT NULL,
  team_id         INTEGER NOT NULL,
  player_id       INTEGER NOT NULL,
  lineup_slot_id  INTEGER NOT NULL,
  is_starter      BOOLEAN NOT NULL,
  points_scored   REAL,
  is_final        BOOLEAN NOT NULL DEFAULT 0,
  fetched_at      TIMESTAMP NOT NULL,
  PRIMARY KEY (league_id, season_year, week, team_id, player_id),
  FOREIGN KEY (league_id, season_year, team_id) REFERENCES teams(league_id, season_year, team_id)
);

CREATE TABLE IF NOT EXISTS raw_team_week (
  league_id       INTEGER NOT NULL,
  season_year     INTEGER NOT NULL,
  week            INTEGER NOT NULL,
  team_id         INTEGER NOT NULL,
  total_points    REAL NOT NULL,
  is_final        BOOLEAN NOT NULL DEFAULT 0,
  source          TEXT NOT NULL,
  fetched_at      TIMESTAMP NOT NULL,
  PRIMARY KEY (league_id, season_year, week, team_id)
);

-- === Matchups and standings ==================================================

CREATE TABLE IF NOT EXISTS raw_matchups (
  league_id     INTEGER NOT NULL,
  season_year   INTEGER NOT NULL,
  week          INTEGER NOT NULL,
  team_a        INTEGER NOT NULL,
  team_b        INTEGER NOT NULL,
  score_a       REAL,
  score_b       REAL,
  winner        TEXT,
  status        TEXT NOT NULL,
  source        TEXT NOT NULL,
  fetched_at    TIMESTAMP NOT NULL,
  PRIMARY KEY (league_id, season_year, week, team_a, team_b)
);

CREATE TABLE IF NOT EXISTS standings_snapshots (
  league_id      INTEGER NOT NULL,
  season_year    INTEGER NOT NULL,
  week           INTEGER NOT NULL,
  team_id        INTEGER NOT NULL,
  wins           INTEGER NOT NULL,
  losses         INTEGER NOT NULL,
  ties           INTEGER NOT NULL,
  points_for     REAL NOT NULL,
  points_against REAL NOT NULL,
  playoff_seed   INTEGER,
  created_at     TIMESTAMP NOT NULL,
  PRIMARY KEY (league_id, season_year, week, team_id)
);

-- === Transactions =============================================================

CREATE TABLE IF NOT EXISTS raw_transactions (
  transaction_id  TEXT PRIMARY KEY,
  league_id       INTEGER NOT NULL,
  season_year     INTEGER NOT NULL,
  week            INTEGER NOT NULL,
  team_id         INTEGER,
  type            TEXT NOT NULL,
  bid_amount      INTEGER,
  status          TEXT NOT NULL,
  proposed_at     TIMESTAMP,
  fetched_at      TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS raw_transaction_items (
  transaction_id  TEXT NOT NULL REFERENCES raw_transactions(transaction_id),
  player_id       INTEGER NOT NULL,
  from_team_id    INTEGER,
  to_team_id      INTEGER,
  item_type       TEXT,                     -- nullable: real data has null here for
                                             -- some paired/cancelled items (fromTeamId=
                                             -- toTeamId=0) — confirmed live, not a bug
  PRIMARY KEY (transaction_id, player_id)
);

-- === Derived ==================================================================

CREATE TABLE IF NOT EXISTS derived_team_week (
  league_id             INTEGER NOT NULL,
  season_year           INTEGER NOT NULL,
  week                  INTEGER NOT NULL,
  team_id               INTEGER NOT NULL,
  actual_starter_points REAL NOT NULL,
  optimal_lineup_points REAL NOT NULL,
  -- Nullable, not NOT NULL: genuinely undefined (not zero) before anyone
  -- in the league has recorded a single point that week — optimal_lineup_
  -- points is a real 0.0 then (no players to assign), and 0.0 is falsy in
  -- Python, so actual/optimal legitimately evaluates to None. Found live
  -- via the first GitHub Actions run, 2026-09-17: week 2 had just started
  -- with zero games played, and this NOT NULL constraint crashed the
  -- whole calculate step. Same nullable pattern derived_team_season.
  -- season_lineup_efficiency already used correctly for the same reason.
  lineup_efficiency     REAL,
  bench_points          REAL NOT NULL,
  score_rank            INTEGER NOT NULL,
  calc_version          TEXT NOT NULL,
  calculated_at         TIMESTAMP NOT NULL,
  PRIMARY KEY (league_id, season_year, week, team_id)
);

CREATE TABLE IF NOT EXISTS derived_team_season (
  league_id                 INTEGER NOT NULL,
  season_year               INTEGER NOT NULL,
  team_id                   INTEGER NOT NULL,
  through_week              INTEGER NOT NULL,
  weeks_played              INTEGER NOT NULL,
  points_for REAL, points_against REAL, avg_pf REAL, avg_pa REAL,
  actual_w INTEGER, actual_l INTEGER, actual_t INTEGER,
  allplay_w INTEGER, allplay_l INTEGER, allplay_t INTEGER,
  expected_wins REAL, luck_index REAL,
  season_lineup_efficiency REAL,
  total_bench_points        REAL,
  is_provisional            BOOLEAN NOT NULL,
  calc_version              TEXT NOT NULL,
  calculated_at             TIMESTAMP NOT NULL,
  PRIMARY KEY (league_id, season_year, team_id, through_week)
);

CREATE TABLE IF NOT EXISTS derived_waiver_moves (
  transaction_id              TEXT PRIMARY KEY REFERENCES raw_transactions(transaction_id),
  player_added                INTEGER NOT NULL,
  player_dropped               INTEGER,
  points_added_over_horizon    REAL,
  points_dropped_over_horizon  REAL,
  net_value                    REAL,
  horizon_weeks                INTEGER NOT NULL,
  is_complete                  BOOLEAN NOT NULL,
  calc_version                 TEXT NOT NULL,
  calculated_at                TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS derived_trade_evaluation (
  trade_group_id        TEXT PRIMARY KEY,
  team_a_id             INTEGER NOT NULL,
  team_b_id             INTEGER NOT NULL,
  team_a_points_gained  REAL,
  team_b_points_gained  REAL,
  horizon_weeks         INTEGER NOT NULL,
  is_complete           BOOLEAN NOT NULL,
  calc_version          TEXT NOT NULL,
  calculated_at         TIMESTAMP NOT NULL
);

-- === Operations ================================================================

CREATE TABLE IF NOT EXISTS ingest_runs (
  run_id        INTEGER PRIMARY KEY AUTOINCREMENT,
  started_at    TIMESTAMP NOT NULL,
  finished_at   TIMESTAMP,
  job_name      TEXT NOT NULL,
  status        TEXT NOT NULL,
  requests_made INTEGER,
  rows_written  INTEGER,
  error_text    TEXT
);

CREATE TABLE IF NOT EXISTS data_issues (
  issue_id     INTEGER PRIMARY KEY AUTOINCREMENT,
  detected_at  TIMESTAMP NOT NULL,
  severity     TEXT NOT NULL,
  category     TEXT NOT NULL,
  league_id INTEGER, season_year INTEGER, week INTEGER, team_id INTEGER,
  description  TEXT NOT NULL,
  resolved     BOOLEAN NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS scoring_events (
  event_id       INTEGER PRIMARY KEY AUTOINCREMENT,
  league_id      INTEGER NOT NULL,
  season_year    INTEGER NOT NULL,
  week           INTEGER NOT NULL,
  team_id        INTEGER NOT NULL,
  player_id      INTEGER NOT NULL,
  is_starter     BOOLEAN NOT NULL,
  points_before  REAL NOT NULL,
  points_after   REAL NOT NULL,
  detected_at    TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS raw_payloads (
  payload_id   INTEGER PRIMARY KEY AUTOINCREMENT,
  league_id    INTEGER,
  endpoint     TEXT NOT NULL,
  params       TEXT,
  fetched_at   TIMESTAMP NOT NULL,
  week         INTEGER,
  body_gzip    BLOB NOT NULL
);
