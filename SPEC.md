# ESPN Fantasy Football — Multi-League Intelligence System
## Locked Specification v1.0

**Date:** 13 September 2026
**Season:** 2026
**Leagues:**
- `1618731` — *No More Domestic Violence* (14 teams, 2 divisions) — your team: *Goff Is My Copilot*
- `581297461` — *My 2023 League* (12 teams) — your team: *LaPorta Authority*

**Owner:** identified by ESPN `SWID` (stable across both leagues, confirmed live)
**Status:** Design locked following Phase 1 API verification (2026-09-13, see `phase1_output/VERIFICATION_REPORT.md`). No schema built yet. Approval required before Phase 2.

---

## 0. Confirmed Requirements

| Topic | Decision |
|---|---|
| Platform | ESPN Fantasy Football, API v3, real host `lm-api-reads.fantasy.espn.com` (found in Phase 1 — `fantasy.espn.com` itself only serves the website) |
| Scope | **Two** private leagues, tracked from day one as first-class, not bolted on later |
| Identity | Your ESPN `SWID` is the cross-league "this is you" key — confirmed live against both leagues' `primaryOwner` fields |
| League type | Both H2H points-based (`scoringType: H2H_POINTS`), not category scoring |
| Auth | Private leagues — `espn_s2` + `SWID` cookies required, loaded from a gitignored `.env`, never committed |
| Update frequency | Once daily, matching the FPL project's cadence |
| Audience | Owner only. No sharing, no multi-user, no publishing |
| Analytics priority | Ledger → Recap → Lineup-efficiency/waiver/trade skill → Luck (week 5+) → Power rankings (week 5+) → Playoff odds (week 7+) — thresholds provisional, see §13 |
| Stack | Python + SQLite + Git, queried through Claude Code, mirroring the FPL project's architecture |

### Standing constraint

Every endpoint's *shape* was verified live in Phase 1 against real data. What was **not** yet verified as of the spec lock: full player-pool pagination — a Phase 3 item, not a schema blocker. (League `581297461`'s playoff format was resolved during Phase 2: 4-team playoff, `TOTAL_POINTS_SCORED` seeding, season runs through week 18 — see §13.)

---

## 1. Product Specification

### What it is

A local, file-based database accumulating a complete, permanent record of two ESPN H2H fantasy football leagues, plus a derived analytics layer, queried in natural language through Claude Code.

### What it must do

1. Record, permanently and without overwriting, every team's roster, starting lineup, and transactions for every week, in both leagues.
2. Record every matchup result and the standings after every week.
3. Compute manager-skill metrics that are exact rather than estimated — lineup efficiency, waiver-pickup value, trade outcomes.
4. Compute luck and strength metrics, but withhold them until the (short, 14-17 week) sample supports them.
5. Answer natural-language questions against real stored data, scoped to either league or both.
6. Never present an estimate as a fact, and never invent a number.

### What it explicitly will not do

- Live in-game scoring (a "live" week shows real partial data, same idea as FPL's provisional gameweeks, but this is not a play-by-play tracker).
- Anything requiring write access to either league — read-only, always.
- FAAB-budget ROI — **neither league uses FAAB** (confirmed Phase 1: both `WAIVERS_TRADITIONAL`), so there is no bid budget to evaluate. Waiver value is measured by outcome instead (§5).
- Player recommendations / start-sit advice as a live feature — this system looks backward at decisions made, not forward at ones to make. (A retrospective "here's what your data says about your decision-making" is in scope; a forward-looking "start X over Y this week" is not, the same boundary FPL drew around projections vs. facts.)

### The three layers, kept separate

| Layer | Definition | Storage | Mutability |
|---|---|---|---|
| **Raw** | What ESPN reported. | `raw_*` tables | Append-only once finalized |
| **Derived** | What our code computed from raw. | `derived_*` tables | Recomputable from scratch |
| **Interpretation** | What Claude says about it. | Never stored as fact | Ephemeral |

One nuance specific to this project, absent from the FPL build: a player's **real-world stat line** (yards, TDs, etc.) is universal — the same regardless of which league you're asking about. What differs *per league* is how many fantasy points those stats are worth, because each league's `scoringItems` weights them differently (confirmed live: league `1618731` and `581297461` score several stat categories differently). So raw stats are stored once, globally, per player per week; fantasy points are a **derived**, per-league calculation applied on top. Getting this backwards — storing "points" as if they were raw — would make it impossible to ever audit a scoring dispute or fix a scoring-rule bug retroactively.

---

## 2. Data Source Architecture

### Source

`https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{year}/segments/0/leagues/{leagueId}?view=...`

Undocumented, no published stability guarantee — same risk profile as FPL's API, mitigated the same way: archive every raw payload so parsing can be replayed after a schema change.

### Endpoints — verified live, Phase 1 (2026-09-13)

| View | Purpose | Status |
|---|---|---|
| `mSettings` | Roster slots, scoring rules, schedule/playoff/waiver/trade config | Verified — differs meaningfully between the two leagues |
| `mTeam` | Team names, `primaryOwner`, `members` | Verified — `primaryOwner` requires this view explicitly; combining `mRoster` alone omits it |
| `mRoster` | Current roster, `lineupSlotId`, injury status | Verified |
| `mMatchup` | Weekly schedule, `totalPoints`, `winner` | Verified — `winner: "UNDECIDED"` and `totalPoints: 0.0` both sides is real, current state (week 1 hasn't scored yet), not a bug |
| `mTransactions2` | Draft picks, waiver moves, trades | Verified — 221 rows already, mostly `DRAFT` |
| `kona_player_info` | Full player pool, ownership %, stats | Verified working, but returns only 50 players per call — pagination unresolved, Phase 3 item |

### Two ID namespaces — confirmed empirically, not from memory

- **`defaultPositionId`** (a player's real position): `1=QB, 2=RB, 3=WR, 4=TE, 5=K, 16=D/ST` — confirmed by sampling real players (Lamar Jackson, Saquon Barkley, Terry McLaurin, Jake Ferguson, Tyler Loop, Jets D/ST), not assumed from community folklore.
- **`lineupSlotId`** (a roster slot type — a different scheme): `0=QB, 2=RB, 4=WR, 6=TE, 16=D/ST, 17=K, 20=Bench, 21=IR, 23=FLEX`.

These are stored in clearly separate, clearly named columns everywhere. Conflating them would silently corrupt every lineup-efficiency number the project exists to produce.

### Fallback — confirmed necessary, not hypothetical

`mMatchup.totalPoints` **cannot be trusted for a live week.** Confirmed live during Phase 3 (2026-09-13, Week 1, both leagues): every single team in both leagues showed `totalPoints: 0.0` in `mMatchup` while each player's own `stats` entry already had real, non-zero `appliedTotal` values for completed games (round numbers like 18.0, 33.0 — clearly actual results, not projections). This is the same shape of bug as the FPL project's `entry_history.points` lag: a coarse summary field ESPN computes on its own schedule, stuck behind the more granular per-player data that's already current.

**Fix, not a workaround:** `raw_team_week.total_points` and `raw_matchups.score_a/score_b` are always computed by summing each team's starters' real per-player `appliedTotal` — never taken directly from `mMatchup.totalPoints`. That field is still fetched and compared; any disagreement beyond rounding is logged as a `data_issue` (confirmed: 26 such warnings (one per team-side) logged across both leagues' Week 1, entirely expected given the field-wide lag, not something to "fix" by suppressing the check).

### Politeness

Sequential requests, ~1 second apart, identifying User-Agent, exponential backoff on failure — same client design as the FPL project, adapted for cookie-based auth.

---

## 3. Database Schema

SQLite, Postgres-shaped. `league_id` and `season_year` are first-class on nearly every table from day one — this was a design mistake worth avoiding twice; the FPL schema had to retrofit multi-league thinking it never used, this one starts with it because it's used immediately.

### 3.1 Reference

```sql
CREATE TABLE leagues (
  league_id       INTEGER PRIMARY KEY,     -- ESPN's own numeric league ID
  name            TEXT NOT NULL,           -- as ESPN reports it, may be stale/joke names
  my_team_hint    TEXT                     -- owner-supplied hint for Phase 1 identification only
);

CREATE TABLE league_seasons (
  league_id             INTEGER NOT NULL REFERENCES leagues(league_id),
  season_year           INTEGER NOT NULL,
  team_count            INTEGER NOT NULL,
  scoring_type          TEXT NOT NULL,           -- 'H2H_POINTS'
  waiver_type           TEXT NOT NULL,           -- 'WAIVERS_TRADITIONAL' | 'WAIVERS_BUDGET' — verify, don't assume, per league
  regular_season_weeks  INTEGER NOT NULL,
  final_week            INTEGER NOT NULL,
  playoff_team_count    INTEGER,
  playoff_seeding_rule  TEXT,                    -- e.g. 'TOTAL_POINTS_SCORED' — confirmed non-default in league 1618731
  trade_veto_votes_required INTEGER,
  roster_slot_counts_json TEXT NOT NULL,         -- raw lineupSlotCounts, since it varies per league (5 vs 7 bench, confirmed)
  scoring_items_json    TEXT NOT NULL,           -- full raw scoringItems array — this is what makes points a derived, not raw, value
  config_json           TEXT,                    -- full settings object as returned
  last_verified         TIMESTAMP,
  PRIMARY KEY (league_id, season_year)
);

CREATE TABLE pro_teams (
  pro_team_id   INTEGER PRIMARY KEY,      -- ESPN's real-NFL team ID
  season_year   INTEGER NOT NULL,
  name          TEXT NOT NULL,
  abbrev        TEXT NOT NULL
);

CREATE TABLE players (
  player_id           INTEGER PRIMARY KEY,     -- ESPN's global player ID — same across every league
  full_name           TEXT NOT NULL,
  default_position_id INTEGER NOT NULL,        -- 1 QB | 2 RB | 3 WR | 4 TE | 5 K | 16 D/ST — confirmed Phase 1
  pro_team_id         INTEGER
);

CREATE TABLE raw_player_snapshots (
  player_id      INTEGER NOT NULL,
  snapshot_date  DATE NOT NULL,
  ownership_pct  REAL,                     -- ESPN's own % rostered, league-universe-wide
  injury_status  TEXT,
  fetched_at     TIMESTAMP NOT NULL,
  PRIMARY KEY (player_id, snapshot_date)
);
```

### 3.2 Managers and teams

Managers are global (keyed by the ESPN `SWID`/member GUID, confirmed stable across leagues) — teams are league+season-scoped, since the same person's roster in League A and League B are entirely different entities.

```sql
CREATE TABLE managers (
  manager_id    INTEGER PRIMARY KEY,      -- our surrogate key
  espn_member_id TEXT NOT NULL UNIQUE,    -- the SWID/GUID, e.g. '{E1AB20C5-...}'
  display_name  TEXT,
  is_owner      BOOLEAN NOT NULL DEFAULT 0 -- exactly one row true
);

CREATE TABLE teams (
  league_id     INTEGER NOT NULL,
  season_year   INTEGER NOT NULL,
  team_id       INTEGER NOT NULL,          -- ESPN's team ID — unique only within this league+season
  manager_id    INTEGER REFERENCES managers(manager_id),
  team_name     TEXT NOT NULL,
  division_id   INTEGER,
  PRIMARY KEY (league_id, season_year, team_id),
  FOREIGN KEY (league_id, season_year) REFERENCES league_seasons(league_id, season_year)
);
```

### 3.3 Raw weekly facts

Real stat lines are universal — not league-scoped. Fantasy points from them are league-specific and computed (§3.4).

```sql
CREATE TABLE raw_player_week_stats (
  season_year   INTEGER NOT NULL,
  week          INTEGER NOT NULL,
  player_id     INTEGER NOT NULL,
  stats_json    TEXT NOT NULL,            -- raw {statId: value} — ESPN's own stat IDs, undecoded
  is_final      BOOLEAN NOT NULL DEFAULT 0,
  source        TEXT NOT NULL,
  fetched_at    TIMESTAMP NOT NULL,
  PRIMARY KEY (season_year, week, player_id)
);

CREATE TABLE raw_roster_entries (
  league_id       INTEGER NOT NULL,
  season_year     INTEGER NOT NULL,
  week            INTEGER NOT NULL,
  team_id         INTEGER NOT NULL,
  player_id       INTEGER NOT NULL,
  lineup_slot_id  INTEGER NOT NULL,        -- roster SLOT scheme, not position — see §2
  is_starter      BOOLEAN NOT NULL,        -- slot not in {Bench, IR}
  points_scored   REAL,                    -- this league's scoring rules applied to raw stats
  is_final        BOOLEAN NOT NULL DEFAULT 0,
  fetched_at      TIMESTAMP NOT NULL,
  PRIMARY KEY (league_id, season_year, week, team_id, player_id),
  FOREIGN KEY (league_id, season_year, team_id) REFERENCES teams(league_id, season_year, team_id)
);

CREATE TABLE raw_team_week (
  league_id       INTEGER NOT NULL,
  season_year     INTEGER NOT NULL,
  week            INTEGER NOT NULL,
  team_id         INTEGER NOT NULL,
  total_points    REAL NOT NULL,           -- ESPN's own reported total for the week
  is_final        BOOLEAN NOT NULL DEFAULT 0, -- true once every game in this week has finished
  source          TEXT NOT NULL,
  fetched_at      TIMESTAMP NOT NULL,
  PRIMARY KEY (league_id, season_year, week, team_id)
);
```

Hit cost has no NFL equivalent — no chips, no transfer penalties. `total_points` is simply the match score; there's no gross/net distinction to get backwards (unlike FPL rule 10 — noted so nobody goes looking for one).

### 3.4 Matchups and standings

```sql
CREATE TABLE raw_matchups (
  league_id     INTEGER NOT NULL,
  season_year   INTEGER NOT NULL,
  week          INTEGER NOT NULL,
  team_a        INTEGER NOT NULL,
  team_b        INTEGER NOT NULL,
  score_a       REAL,
  score_b       REAL,
  winner        TEXT,                      -- 'HOME' | 'AWAY' | 'UNDECIDED' | 'TIE', as ESPN reports it
  status        TEXT NOT NULL,              -- scheduled | provisional | final
  source        TEXT NOT NULL,
  fetched_at    TIMESTAMP NOT NULL,
  PRIMARY KEY (league_id, season_year, week, team_a, team_b)
);

CREATE TABLE standings_snapshots (
  league_id      INTEGER NOT NULL,
  season_year    INTEGER NOT NULL,
  week           INTEGER NOT NULL,          -- standings AFTER this week
  team_id        INTEGER NOT NULL,
  wins           INTEGER NOT NULL,
  losses         INTEGER NOT NULL,
  ties           INTEGER NOT NULL,
  points_for     REAL NOT NULL,
  points_against REAL NOT NULL,
  playoff_seed   INTEGER,                   -- NULL until the league's own seeding is computed by ESPN
  created_at     TIMESTAMP NOT NULL,
  PRIMARY KEY (league_id, season_year, week, team_id)
);
```

### 3.5 Transactions — waivers, trades, drafts

```sql
CREATE TABLE raw_transactions (
  transaction_id  TEXT PRIMARY KEY,         -- ESPN's own UUID
  league_id       INTEGER NOT NULL,
  season_year     INTEGER NOT NULL,
  week            INTEGER NOT NULL,          -- scoringPeriodId at proposal time
  team_id         INTEGER,
  type            TEXT NOT NULL,             -- DRAFT | WAIVER | FREEAGENT | TRADE
  bid_amount      INTEGER,                   -- always 0 for both these leagues (no FAAB), stored anyway in case that ever changes
  status          TEXT NOT NULL,             -- EXECUTED | PENDING | ...
  proposed_at     TIMESTAMP,
  fetched_at      TIMESTAMP NOT NULL
);

CREATE TABLE raw_transaction_items (
  transaction_id  TEXT NOT NULL REFERENCES raw_transactions(transaction_id),
  player_id       INTEGER NOT NULL,
  from_team_id    INTEGER,                  -- 0 = free agent pool, per ESPN's own convention
  to_team_id      INTEGER,
  item_type       TEXT NOT NULL,            -- as ESPN reports it
  PRIMARY KEY (transaction_id, player_id)
);
```

### 3.6 Derived

```sql
CREATE TABLE derived_team_week (
  league_id           INTEGER NOT NULL,
  season_year         INTEGER NOT NULL,
  week                INTEGER NOT NULL,
  team_id             INTEGER NOT NULL,
  actual_starter_points REAL NOT NULL,
  optimal_lineup_points REAL NOT NULL,      -- best legal lineup from the same roster, respecting eligibleSlots
  lineup_efficiency   REAL NOT NULL,        -- actual / optimal — the FPL project's XI-efficiency analog; there's no captain, so this is THE core "did you set your lineup right" number
  bench_points        REAL NOT NULL,
  score_rank          INTEGER NOT NULL,     -- 1..N that week, within this league
  calc_version        TEXT NOT NULL,
  calculated_at       TIMESTAMP NOT NULL,
  PRIMARY KEY (league_id, season_year, week, team_id)
);

CREATE TABLE derived_team_season (
  league_id            INTEGER NOT NULL,
  season_year          INTEGER NOT NULL,
  team_id              INTEGER NOT NULL,
  through_week         INTEGER NOT NULL,
  weeks_played         INTEGER NOT NULL,     -- confidence gate for every estimate
  points_for REAL, points_against REAL, avg_pf REAL, avg_pa REAL,
  actual_w INTEGER, actual_l INTEGER, actual_t INTEGER,
  allplay_w INTEGER, allplay_l INTEGER, allplay_t INTEGER,   -- withheld below the gate, §5
  expected_wins REAL, luck_index REAL,                        -- withheld below the gate
  season_lineup_efficiency REAL,
  total_bench_points REAL,
  is_provisional       BOOLEAN NOT NULL,
  calc_version         TEXT NOT NULL,
  calculated_at        TIMESTAMP NOT NULL,
  PRIMARY KEY (league_id, season_year, team_id, through_week)
);

CREATE TABLE derived_waiver_moves (
  transaction_id      TEXT PRIMARY KEY REFERENCES raw_transactions(transaction_id),
  player_added        INTEGER NOT NULL,
  player_dropped       INTEGER,
  points_added_over_horizon   REAL,          -- added player's points over N weeks (configurable horizon)
  points_dropped_over_horizon REAL,          -- what the dropped player scored over the same span, elsewhere
  net_value            REAL,                 -- added minus dropped — the outcome-based replacement for FAAB ROI
  horizon_weeks         INTEGER NOT NULL,
  is_complete           BOOLEAN NOT NULL,    -- false until the full horizon has elapsed
  calc_version          TEXT NOT NULL,
  calculated_at         TIMESTAMP NOT NULL
);

CREATE TABLE derived_trade_evaluation (
  trade_group_id       TEXT PRIMARY KEY,     -- groups the paired transaction_ids of one trade
  team_a_id            INTEGER NOT NULL,
  team_b_id            INTEGER NOT NULL,
  team_a_points_gained REAL,                 -- players received minus players given up, over the horizon
  team_b_points_gained REAL,
  horizon_weeks         INTEGER NOT NULL,
  is_complete           BOOLEAN NOT NULL,
  calc_version          TEXT NOT NULL,
  calculated_at          TIMESTAMP NOT NULL
);
```

Plus `derived_power_rankings` and `derived_playoff_projections` (model-versioned, defined in Phase 8 once real data shows what's worth modeling, same discipline as FPL's Tier 4/5).

### 3.7 Operations

```sql
CREATE TABLE ingest_runs (
  run_id        INTEGER PRIMARY KEY AUTOINCREMENT,
  started_at    TIMESTAMP NOT NULL,
  finished_at   TIMESTAMP,
  job_name      TEXT NOT NULL,
  status        TEXT NOT NULL,             -- success | partial | failed
  requests_made INTEGER,
  rows_written  INTEGER,
  error_text    TEXT
);

CREATE TABLE data_issues (
  issue_id     INTEGER PRIMARY KEY AUTOINCREMENT,
  detected_at  TIMESTAMP NOT NULL,
  severity     TEXT NOT NULL,              -- info | warning | error
  category     TEXT NOT NULL,
  league_id INTEGER, season_year INTEGER, week INTEGER, team_id INTEGER,
  description  TEXT NOT NULL,
  resolved     BOOLEAN NOT NULL DEFAULT 0
);

CREATE TABLE raw_payloads (
  payload_id   INTEGER PRIMARY KEY AUTOINCREMENT,
  league_id    INTEGER,
  endpoint     TEXT NOT NULL,
  params       TEXT,
  fetched_at   TIMESTAMP NOT NULL,
  week         INTEGER,
  body_gzip    BLOB NOT NULL
);
```

---

## 4. Historical Integrity

Same five mechanisms as the FPL project, adapted:

1. **Finalization gate.** A week's data is provisional (`is_final = 0`) until every game in that week has finished — not one single deadline like FPL's gameweeks, since NFL games kick off across Thursday/Sunday/Monday. A "final" week means every real-world game feeding it is over.
2. **Application-level immutability.** No UPDATE on any `is_final = 1` row, ever — a disagreement becomes a `data_issues` row, not a silent correction.
3. **Natural keys everywhere.** Every raw table's primary key is its natural key — idempotent upserts, safe to rerun.
4. **Snapshot, don't mutate.** Player ownership/injury state is dated rows, never overwritten fields.
5. **Provenance.** `source` and `fetched_at` on every raw row.

Target questions:

- *"What was my Week 3 lineup in League A?"* → `raw_roster_entries` where league_id/week=3
- *"Who was leading League B after Week 5?"* → `standings_snapshots` where week=5
- *"Did I have the right optimal lineup in Week 2?"* → `derived_team_week.lineup_efficiency`

---

## 5. Analytics — Methodology

No captain, no chips — the FPL-specific mechanics don't exist here. What replaces them:

### Tier 0 — Ledger (exact, from week 1)

Points for/against, margins, bench points, rank movement. No assumptions.

### Tier 1 — Weekly recap (from week 1)

Week's high/low score, biggest blowout, closest margin, unluckiest loss (highest score among that week's losers), luckiest win (lowest score among that week's winners) — direct analogs of the FPL recap, per league.

### Tier 2 — Manager skill (exact, from week 1) — priority tier

**Lineup efficiency** = actual starting-lineup points ÷ best possible legal lineup from the same full roster that week, respecting `eligibleSlots`. This is the single most important metric in the whole system — with no captain multiplier, it's the entire "did you make the right call" story that FPL split across captain-efficiency and XI-efficiency.

**Points left on bench** = sum of bench/IR players' actual scores (not their zeroed lineup contribution).

**Waiver value** (replaces FAAB ROI, since neither league uses FAAB): for each add/drop pair, the added player's points over a stated horizon (default 3 weeks, configurable) minus the dropped player's points over the same span, wherever they ended up. Reported with the horizon stated, and as incomplete until it's elapsed — same "don't report early" discipline as FPL's Transfer ROI.

**Trade evaluation**: for each trade, each side's points gained (players received minus players given up) over a stated horizon. No single "won the trade" verdict when the horizon isn't complete; report both sides' numbers with the horizon stated.

### Tier 3 — Luck and true strength (computed from week 1, hidden until the gate opens)

All-play record, expected wins, luck index — same formulas as FPL, computed weekly against all other teams in that specific league (never across leagues — that comparison means nothing, different schedules and rosters entirely).

### Tier 4 — Power rankings (gated)

Same four-model structure as FPL (statistical / form / roster strength / hybrid), scoped per league.

### Tier 5 — Playoff odds (gated)

Monte Carlo over each league's own remaining schedule and its own playoff format (team count, seeding rule) — the two leagues' playoff structures are already confirmed different (§0), so this can never be a shared calculation.

### Confidence gating

| Tier | Provisional minimum weeks | Below threshold |
|---|---|---|
| 0 Ledger | 1 | Always shown |
| 1 Recap | 1 | Always shown |
| 2 Skill | 1 (waiver/trade: horizon+1) | Shown; incomplete-horizon items marked so |
| 3 Luck | 5 | **Withheld** |
| 4 Power | 5 | **Withheld** |
| 5 Playoff odds | 7 | **Withheld** |

Confirmed by the owner 2026-09-13, along with the 3-week waiver/trade ROI horizon (§13).

---

## 6. Automation

Same daily-job shape as FPL: fetch both leagues' current state, determine which weeks are newly final, write with `is_final=1`, recompute derived tables, log the run. GitHub Actions + a committed SQLite file, same reasoning as before (no machine needs to stay awake, commit history is a second audit trail).

One real difference: **the credential**. FPL needed none; this needs `ESPN_S2`/`ESPN_SWID` available to the scheduled job. GitHub Actions repository secrets are the standard place for this — never committed, injected as environment variables at run time.

---

## 7. Claude Integration

Same shape as FPL: Claude Code against the repo, a `CLAUDE.md` with the schema/rules/gates, a `queries/` library, `reports/week{N}_{league}.md` recaps, `digest/season.json` per league (or one combined digest with a league key — TBD in Phase 7).

Every question maps to a direct lookup: *"What was my lineup in Week 4 of the copilot league?"*, *"How's my waiver record this year?"*, *"Compare my two teams' luck so far"* (once the gate opens) are all real queries over this schema, nothing improvised.

---

## 8. Dashboard

Self-contained HTML file, same reasoning as FPL (baked-in data, no server, `file://`-safe). Fresh visual identity for this project — not a reskin of the FPL dashboard (owner's call). A league switcher replaces FPL's single-league assumption; every other page (Home, My Team, League, Managers-equivalent, Players, Analytics, History) carries a `league_id` in its own state.

Roster views show real team logos (already present in ESPN's `mTeam` response — a `logo` field observed on every team) rather than jersey art, since ESPN doesn't expose the same kind of per-club kit CDN FPL's Premier League data did; player photos are ESPN's own headshot CDN and are opt-in, not default, per the earlier decision to keep player-photo usage a deliberate choice rather than an assumption.

---

## 9. Security

- **Real credentials this time** — `ESPN_S2`/`ESPN_SWID` are session cookies, stored only in a gitignored `.env` locally and as GitHub Actions repository secrets for the scheduled job. Never logged, never printed, never committed.
- **Read-only.** The client only ever GETs. Nothing here can modify either league, place a waiver claim, or execute a trade.
- **No inbound surface.** Nothing listens on a port.
- **Private repo**, same as FPL.

---

## 10. Cost

Same as FPL: $0 ongoing. Free API, free SQLite, free GitHub Actions tier, Claude Code included in the existing subscription.

---

## 11. Roadmap

**Phase 0 — Environment.** ✅ Complete 2026-09-13. Git repo, Python 3.13 venv, `requests` + `python-dotenv`, `.env.example`.

**Phase 1 — Verify the API.** ✅ Complete 2026-09-13. Real host found (`lm-api-reads.fantasy.espn.com`), auth confirmed, cross-league identity resolved via SWID, both ID namespaces empirically mapped, core endpoints verified against both leagues. See `phase1_output/VERIFICATION_REPORT.md`.

**Phase 2 — Schema and league/team resolution.** ✅ Complete 2026-09-13. `db/schema.sql` applied; `src/build_db.py` resolved both leagues live — 26 teams stored across the two leagues, your SWID matched your team in both (`Goff Is My Copilot` in `1618731`, `LaPorta Authority` in `581297461`), zero `data_issues` logged. Resolved league `581297461`'s playoff format as a side effect: 4-team playoff, `TOTAL_POINTS_SCORED` seeding, season runs through week 18 (vs. league `1618731`'s week-17 finish and 8-team playoff) — confirmed different, not assumed.
*Exit: both leagues' teams and managers stored, your identity confirmed correct in both.*

**Phase 3 — Historical backfill.** ✅ Complete 2026-09-13, scoped honestly: the season is genuinely at Week 1 for both leagues (`currentMatchupPeriod: 1` — there is no finalized history yet to backfill, only a live week to capture provisionally, same idea as an FPL provisional gameweek). `src/backfill.py` ingested Week 1's rosters/lineups/matchups/transactions for both leagues (33 real NFL teams, 26 team rosters, 458 transactions total, 26 standings rows) and, in the process, **confirmed and fixed a real, systemic bug**: `mMatchup.totalPoints` was `0.0` for every team in both leagues while real per-player stats were already populated — `raw_team_week`/`raw_matchups` now always compute totals from summed roster points instead, with the disagreement logged as 26 `data_issues` (one per team-side, every single one flagged) rather than silently trusted or silently fixed (see §2 Fallback, CLAUDE.md rule 7).

**Scope note:** the `players` table is populated only from players who actually appear on a roster in one of the two leagues, not ESPN's full free-agent universe — `kona_player_info`'s pagination (deferred from Phase 1) is only needed once a feature requires seeing undrafted free agents, which isn't yet the case. Revisit if/when a waiver-suggestion-adjacent feature needs it.
*Exit: every played week present for both leagues, all validators pass.* ✅ — team counts match `league_seasons`, roster data present for week 1 in both leagues, zero unexpected validator failures (the 26 total-points `data_issues` are the expected, documented finding above, not a validator failure).

**Phase 4 — Automation.** ✅ Locally complete 2026-09-13; not yet scheduled (see below). `src/daily_sync.py` skips any week already fully final in storage and always refreshes the current live week. Ran 3 consecutive times: correctly picked up real in-progress score changes on the still-live Week 1 (one team's total legitimately moved 97.0→98.0 between two runs seconds apart — an actual live game, not a bug), so the FPL-style "byte-identical reruns" test doesn't apply yet — there's no finalized week to test it against. What's verified instead: no duplicate rows on rerun, `data_issues` no longer grows unboundedly for an ongoing condition (found and fixed — see below), and every provisional table's upsert carries its `is_final`/`status`-guard (`raw_player_week_stats`, `raw_roster_entries`, `raw_team_week`, `raw_matchups`), so once a row does flip final it structurally cannot be overwritten by a later run. The true byte-identical test is meaningful once Week 1 actually finalizes.

**Found and fixed while testing reruns:** `data_issues` logging was purely append-only, which is right for discrete one-off events but wrong for an *ongoing condition* — the Week 1 `mMatchup.totalPoints` mismatch (§2) is true on every sync for as long as the week stays live, so 3 reruns logged 26 fresh duplicate rows each time (78 total) before the fix. Added `log_issue_deduped()`: updates the existing unresolved row for the same (category, league, week, team) instead of appending a near-identical one. Discrete-event issues (a failed fetch, etc.) still use plain always-insert logging.

**GitHub Actions workflow is written (`.github/workflows/daily.yml`, cron 06:05 UTC) but not yet active** — this repo has no remote yet, and activating it means pushing code to GitHub and storing `ESPN_S2`/`ESPN_SWID`/`SEASON_YEAR` as repository secrets. Both are real, consequential steps (unlike the FPL project's environment, this one genuinely has `gh` access to do them) — held for explicit confirmation before doing either, rather than done automatically as part of "building Phase 4."
*Exit: three consecutive clean automated runs.* ✅ locally — GitHub scheduling itself is a separate, not-yet-taken step.

**Phase 5 — Tier 0–2 analytics.** ✅ Complete 2026-09-13. `src/calculate.py` computes `derived_team_week` (exact optimal lineup via a bitmask DP over real per-player `eligible_slots_json`, not a hand-guessed position map), `derived_team_season`, and `derived_waiver_moves`. Hand-verified against raw data for team 25 (league `1618731`): actual 137.0 / optimal 157.0 = 87.3% efficiency, bench 62.0 — both traced by hand to the exact underlying roster decisions (started Mayer for 9 over the benched Likely's 24 at TE, plus a suboptimal WR/FLEX split) and matched the code's output exactly. Re-ran the full pipeline (`daily_sync` → `calculate`) and confirmed the same numbers came back unchanged, with no duplicate rows (26 `derived_team_week` rows, exactly 14+12 team-weeks). `derived_trade_evaluation` correctly has zero rows — no trade has actually executed yet this season (only `PENDING`/`CANCELED` proposals exist), an honest empty state, not a bug.
*Exit: manually verified correct, gates confirmed by the owner.* ✅

**Phase 6 — Claude interface.** ✅ Complete 2026-09-13. 8 named, parameterized queries in `queries/` (roster by week, standings, lineup-efficiency leaderboard, week extremes, matchup history, waiver-move outcomes, open data issues, confidence-gate status) — all 8 executed successfully against live data via `src/vet_queries.py`. `src/recap.py` generates `reports/week{N}_{league_id}.md` for finalized weeks only; correctly produced 0 reports right now since Week 1 is still live in both leagues (verified the content-generation logic directly against real data separately from the finalization gate, since it hasn't had a final week to run against yet — real output confirmed sensible: 157.0 high, 55.0 low, 100% best lineup efficiency).
*Exit: real questions answered accurately from real data, across both leagues.* ✅

**Phase 7 — Dashboard.** ✅ Complete 2026-09-13. `src/digest.py` builds `digest/season.json` covering both leagues (standings, this week's live matchups, rosters, lineup-efficiency leaderboard, waiver moves, alerts), embedding team logos as base64 — found live that ESPN's logo CDN needs the same auth as the API, so URLs alone wouldn't work in a static file. `src/build_dashboard.py` builds the self-contained `dashboard.html`: fresh dark-navy/amber visual identity (not a reskin of FPL's), five pages, a league switcher. Found and fixed a second instance of the live-week ESPN-lag bug while building this phase (`standings_snapshots.points_for/against` — same pattern as Phase 3's `mMatchup.totalPoints`, now generalized as a standing rule in CLAUDE.md rather than treated as a one-off). Also found and fixed a missing `<meta charset="utf-8">` that caused visible mojibake (`Â·` for `·`) in the local preview — caught by actually looking at the rendered page, not just running the generator. Verified in-browser across all 5 pages, both leagues, and the Managers dropdown, with every number matching the Phase 5 hand-verification exactly (137.0/157.0/87.3%/62.0/rank 3 of 14).
*Exit: opens, renders both leagues' current state, gates respected.* ✅

**Phase 8 — Tier 3–5.** Luck framework, power rankings, playoff odds — per league, using each league's own confirmed playoff format.
*Exit: methodology documented, outputs labeled, sample sizes stated.*

---

## 12. MVP

**Phases 1–3 plus a minimal query layer**, exactly as FPL defined it: verified endpoints, populated database for both leagues, complete week-1-to-now history, and the ability to ask "what was my roster in Week 2 of the LaPorta league" and get a correct answer. History not captured now is gone forever; everything above MVP can be added later from stored data.

---

## 13. Open Items and Assumptions

**Resolved in Phase 1 (2026-09-13):** real API host; auth mechanism; cross-league identity via SWID; both leagues' roster/scoring/waiver configuration; the position-ID vs. lineup-slot-ID distinction; core endpoint shapes.

**Resolved by the owner (2026-09-13):** the confidence-gate thresholds in §5 (5 weeks for Luck/Power, 7 for Playoff odds) and the waiver/trade ROI horizon (3 weeks) — approved as proposed, scaled down proportionally from FPL's GW10/GW15/5-gameweek-horizon to fit a 14-17 week season.

**Resolved in Phase 2 (2026-09-13):** league `581297461`'s playoff format — 4-team playoff, `TOTAL_POINTS_SCORED` seeding, season through week 18. Confirmed different from league `1618731` (8-team playoff, week 17 finish), not assumed to match.

**Open, to resolve in Phase 3:**
- Full player-pool pagination (`kona_player_info` returns 50 players per call; likely needs an `X-Fantasy-Filter` header, unconfirmed).
- `scoringItems`' `statId` meanings (e.g. `53`, `72`, `89`, `123`, `133`) have no embedded label in the API response — will be cross-referenced against real player stat lines once real games are played, the same way FPL's `net_points` was cross-checked against reported scores.

**Accepted risks:** ESPN's API is undocumented and can change without notice — mitigated by payload archiving, same as FPL. Two leagues' differing configs mean every query must filter by `league_id` — a real discipline cost, accepted in exchange for one shared codebase and one dashboard.

**Deliberately excluded:** FAAB-budget analysis (doesn't apply to either league), live in-game tracking, write access of any kind, cross-league score comparison (different scoring rules make raw point totals incomparable — only rank/efficiency/percentile metrics are safe to compare across your two teams).

---

*Design locked 13 September 2026, following live Phase 1 verification. Approval required before Phase 2 begins.*
