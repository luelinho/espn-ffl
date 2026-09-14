# Operating rules for this repository

This is a data-integrity project first and an analytics project second. The value
of the database is that it can be trusted. These rules protect that.

Read `SPEC.md` for the full design. Read this file before answering any question
about either league.

---

## 1. The three layers

| Layer | Meaning | Where it lives |
|---|---|---|
| **Raw** | What ESPN actually reported | `raw_*` tables |
| **Derived** | What our code computed from raw | `derived_*` tables |
| **Interpretation** | Analysis, opinion, banter | Your response only — never stored as fact |

Never let these mix. Derived tables must be fully reproducible by deleting them
and rerunning the calculators over raw data.

**The one nuance unique to this project:** a player's real-world stat line is
raw and universal — the same number regardless of which league you're asking
about. Fantasy *points* from that stat line are **derived**, because each
league scores stats differently (confirmed live, Phase 1: `1618731` and
`581297461` weight several `statId`s differently). Never store a "points"
number as if it were a raw fact — it's always the output of applying one
specific league's `scoring_items_json` to a raw stat line.

## 2. Never invent a number

If the answer isn't in the database, the answer is "that isn't in the database."

- Do not estimate to fill a gap.
- Do not infer a statistic that wasn't computed.
- Do not produce a number for banter or narrative that no query returns.
- If a query returns nothing, say it returned nothing.

## 3. Separate what happened from what's estimated

- **Fact** — stored raw data. "You scored 87.4 in Week 3."
- **Computed** — derived from facts by a documented formula. "Your lineup
  efficiency is 91%."
- **Projection** — a model output with assumptions. "Simulations give you a
  22% playoff chance."
- **Opinion** — your read. Say so.

Never present a projection in the grammar of a fact.

## 4. Confidence gates

Every derived season row carries `weeks_played` and `is_provisional`. Respect
them.

| Metrics | Minimum weeks | Below that |
|---|---|---|
| Ledger, recap, lineup efficiency, waiver/trade value | 1 | Show normally |
| Luck, all-play, expected wins, power rankings | 5 | **Withhold** |
| Playoff odds | 7 | **Withhold** |

Confirmed by the owner 2026-09-13 (see SPEC.md §13). Below the threshold,
say "insufficient sample — N weeks, need M." Do not show the number with a
caveat attached.

## 5. Never overwrite finalized history

Rows with `is_final = 1` are immutable. Do not UPDATE them. If ESPN's current
data disagrees with a finalized row, write a `data_issues` row and surface
it.

**Provisional weeks.** A week is provisional (`is_final = 0`) until every
NFL game feeding it has finished — not one single deadline like a weekly
gameweek, since NFL games kick off Thursday, Sunday (multiple windows), and
Monday. Never treat a week as fully settled just because *a* deadline has
passed; check that every game in it is actually over.

## 6. Idempotency

Every write is an upsert on a natural key. Running any job twice must
produce identical state.

## 7. Don't guess at the ESPN API

Every field's meaning must be observed in a real response before code
depends on it. Two real examples from Phase 1 of why this matters:

- The real data host is `lm-api-reads.fantasy.espn.com` — `fantasy.espn.com`
  itself only serves the website and redirects.
- `defaultPositionId` (a player's real position: `1=QB, 2=RB, 3=WR, 4=TE,
  5=K, 16=D/ST`) and `lineupSlotId` (a roster slot type: `0=QB, 2=RB, 4=WR,
  6=TE, 16=D/ST, 17=K, 20=Bench, 21=IR, 23=FLEX`) are two different,
  similarly-numbered schemes. Confirmed by sampling real players, not
  assumed from memory or community folklore. Conflating them silently
  breaks every lineup-efficiency number in the system.
- **No ESPN-reported season aggregate can be trusted during a live week —
  this has now bitten twice, in two different fields.** `mMatchup.totalPoints`
  (Phase 3) and `standings_snapshots`'s source, `record.overall.pointsFor`
  (Phase 7), both showed `0.0`/stale values while more granular data (real
  per-player `appliedTotal`, our own `raw_team_week` totals) was already
  correct. Same shape of bug as the FPL project's `entry_history.points`
  lag, confirmed a second time in a different field — treat it as a general
  rule, not a one-off: **`derived_team_season.points_for/points_against`
  are computed from `raw_team_week`/`raw_matchups`, never taken from
  `standings_snapshots` directly.** `standings_snapshots.wins/losses/ties`
  IS still trusted from ESPN, since a decided result isn't subject to this
  lag the way a running point total is — only fields that accumulate
  *during* a live week are suspect. If a third such field turns up, assume
  the same pattern applies rather than re-litigating it as a new bug.

## 8. Phase discipline

Do not start a phase before the previous one is verified working with
observed output. Never claim something works unless it has actually been
run.

## 9. Key facts about these leagues

- Both are ESPN Fantasy Football, H2H points-based, season 2026
- League `1618731` — *No More Domestic Violence* — 14 teams, 2 divisions
  (Stars/Stripes), 15-man roster (5 bench), 8-team playoff, playoff
  **seeded by total points scored, not win/loss record** — confirmed live,
  not the default assumption
- League `581297461` — *My 2023 League* — 12 teams, 17-man roster (7
  bench), season runs through week 18 (one week longer than league
  `1618731`'s week-17 finish), **4-team playoff** seeded by total points
  scored — confirmed different from league `1618731`'s 8-team playoff
- Owner identified by ESPN `SWID` — confirmed stable across both leagues by
  matching it against `primaryOwner` live in each
- **Neither league uses FAAB.** Both are `WAIVERS_TRADITIONAL` (confirmed
  live). There is no bid budget to evaluate — waiver value is measured by
  outcome (added player's points vs. dropped player's points over a stated
  horizon), not by budget efficiency.
- No captain, no chips — these FPL-specific mechanics don't exist here.
  Lineup efficiency (actual starting points ÷ best legal lineup from the
  same roster) carries the full weight that FPL split across captain
  efficiency and XI efficiency.

## 10. No gross/net distinction

There's no transfer-hit cost in NFL fantasy — `total_points` is simply the
match score. Don't go looking for a gross-vs-net split; it doesn't exist
here, unlike FPL rule 10.

## 11. Cross-league comparisons

Raw point totals are **not** comparable between the two leagues — they use
different scoring rules (confirmed live, Phase 1), so 100 points in one
league isn't the same achievement as 100 in the other. Rank, percentile,
and efficiency metrics (which are already normalized within a league) are
safe to compare across your two teams; raw point totals are not.

## 12. Tone

Direct and concrete. The owner is the only user and knows fantasy football
well. Skip the preamble, lead with the answer, keep caveats short but never
drop the ones that matter. Banter is welcome, but only over real numbers.

## 13. The dashboard

`dashboard.html` is a single self-contained file (data baked in, no server)
with five pages: Home, My Team, League, Managers (dropdown over every team
in the current league, reusing My Team's exact render function), Analytics.
A league switcher in the header re-renders whichever page is active for
either league — every render function reads `currentLeague` fresh, nothing
is cached per-league.

**Home is the one exception, deliberately** (owner's call, 2026-09-14):
it ignores the league switcher entirely and always shows both leagues side
by side — your own matchup, position-by-position vs. this week's opponent
(`matchupComparisonCard()`), then both leagues' full scoreboards below.
Nothing else lives on Home; KPI cards, the lineup-efficiency ring, roster
bar list, weekly history, and the league-scores dot matrix only exist on
My Team/Managers/Analytics now. Alerts (`data_issues`) aren't surfaced on
the dashboard at all as of this decision — still fully queryable via
`queries/open_data_issues.sql`, just not shown in the UI.

**Visual identity, redesigned 2026-09-14** from an owner-supplied reference
image: an app-shell layout — a fixed left sidebar (collapses to a
horizontal scrollable bar below 820px, never just hidden — a bare
`display:none` there was a real regression caught live, see below), a
topbar with the league switcher and an owner profile chip, gradient KPI
cards, and real chart components (`ringChart`/`barList`/`dotMatrix`/
`weeklyBarHistory` in the JS) — every one driven by actual digest numbers,
no fabricated trend deltas or placeholder history. Dark navy/violet ground,
amber/blue-purple/cyan/pink gradients — not a reskin of the FPL dashboard's
purple/lime (owner's explicit call). Team logos are embedded as base64 at
digest build time (`src/digest.py`), same reasoning as club badges in the
FPL project — ESPN's logo CDN needs the same auth cookies as the API, so a
plain browser opening the finished file could never load them by URL. Two
of 26 teams' logos are dead third-party links (not our bug) and fall back
to a plain "?" placeholder.

**Live-refresh mode, opt-in, game-day only.** The page embeds `<meta
http-equiv="refresh" content="{LIVE_REFRESH_SECONDS}">` (default 240s = 4
minutes, config.py) and persists the active tab/league to `localStorage`
across reloads — otherwise every auto-reload would silently dump you back
to Home/the first league. That reload only shows new data if
`src/live_refresh.py` is actually running in the background (a separate,
manually-started loop — see below); otherwise it's a harmless reload of
identical content, and the topbar says so. This does NOT change the
scheduled daily job's cadence.

It is a snapshot, not a live view by default — regenerate it after any data change:

```bash
python -m src.daily_sync
python -m src.calculate
python -m src.recap
python -m src.digest
python -m src.build_dashboard
```

For game-day, run the whole chain on a loop instead: `python -m
src.live_refresh` (Ctrl+C to stop; `--interval` overrides the default
240s). It shares `config.LIVE_REFRESH_SECONDS` with the page's own
auto-reload so the two can never drift out of sync — change the interval
in one place, not two.

If you edit `src/build_dashboard.py`, always run `build_dashboard` again
afterward and re-open the file — editing the generator does not change the
already-written `dashboard.html` on disk. **Always include `<meta
charset="utf-8">` in the HTML output** — omitting it was caught live: a
plain local `http.server` preview rendered `·`/`—` as mojibake (`Â·`)
without it, exactly the kind of bug that's invisible until someone actually
looks at the rendered page. **Never hide primary navigation at a
breakpoint without a working replacement** — the same class of bug,
caught the same way: `display:none` on the sidebar below 820px looked fine
in a screenshot and was still a real dead end, since nothing else let you
reach any tab but Home at that width.

**Real per-game status, live vs. finished (2026-09-14).** `raw_pro_games`
(new table) holds ESPN's real per-game state from `proTeamSchedules` —
`inProgress`, `detail`, `percentComplete`, scores, kickoff — fetched by
`ingest.load_pro_games()` once per distinct current week per sync, since a
game's status is universal, not league-scoped. `digest.game_status_map()`
turns this into `pro_team_id -> 'not_started' | 'live' | 'final'` per
player. **Bug found live:** an exact `detail == 'Final'` check missed
overtime games (`detail` is literally `'Final/OT'` there) — a Lions/Bills
OT game showed as `not_started` even with real settled stats already
recorded (Jared Goff, 18.0 pts). Fixed by using `percent_complete >= 100`
as the primary signal instead; `detail` is stored for display only. The
dashboard dims not-started players, puts a pulsing dot on live ones (their
points can still change), and leaves final ones plain.

**Two real logo bugs found and fixed (2026-09-14).** Both were live in
production, not caught until actually inspecting the cached files.
(1) `digest.fetch_logo_b64()` always wrapped the cached bytes as
`data:image/png;base64,...` regardless of the source's actual type — but
roughly half of real team logos are SVGs (custom logo-pack uploads), and a
raster PNG decoder can't parse raw SVG XML, so those rendered as a
broken/missing image in the browser. Fixed by deriving the real MIME type
from the URL extension (`mimetypes.guess_type`). (2) The cache filename was
keyed only by `team_id`, but ESPN team IDs are assigned per-league
starting at 1, so both leagues' team 1, team 12, etc. silently shared (and
could steal) each other's cached logo — a correctness bug, not just a
missing-icon one. Fixed by keying the cache on `(league_id, team_id)`.
Two of 26 teams still show the "?" placeholder — those are genuinely dead
third-party logo URLs (an expired Twitter image, an SSL-dead meme host),
not a bug in our code.

**Per-player real stat lines, opponent/game context, and injury status
(2026-09-14).** Every roster entry now carries a compact stat line (e.g.
"206 YDS, 2 TD" for a QB, "5 REC, 63 YDS" for a WR), the real game context
("@CAR 59-37 Final" or, pre-kickoff, "Mon 8:15 PM" in the viewer's own
timezone), and injury status (Q/D/O/IR badges). Two real gaps closed to
get there:
- `raw_player_week_stats.stats_json` (ESPN's numeric stat-ID blob) was
  already being stored but never parsed into anything human-readable.
  ESPN doesn't publish a stat-ID reference, and CLAUDE.md rule 7 says don't
  guess at the API — so `digest._stat_line()`'s ID-to-category mapping was
  derived by cross-checking real week-1 box scores line-by-line against
  the owner's own ESPN app screenshot (Jared Goff 206 YDS/2 TD, Brock Purdy
  205/3/INT, D'Andre Swift's exact 124 YDS/3 TD, A.J. Brown's exact 3
  REC/26 YDS, Cam Little's exact 2/2 FG · 4/4 XP, the Jaguars D/ST's exact
  INT/FR/10 PA), not assumed from memory. Every category shown was
  confirmed against a real number before being trusted; anything not
  confirmed (e.g. fumbles) was left out rather than guessed.
- `raw_player_snapshots` (injury status, ownership %) existed in schema
  since Phase 2 but nothing ever wrote to it — `mRoster`'s player object
  already carries `injuryStatus` and `ownership.percentOwned`, just wasn't
  being persisted. `ingest.load_week()` now captures one row per player
  per calendar day.
