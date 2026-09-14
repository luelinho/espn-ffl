# Phase 1 — API Verification Report

Verified live 2026-09-13 against both real leagues. Every finding below was
observed in an actual response, archived under `phase1_output/payloads/`.

## The real API host

`fantasy.espn.com` itself only serves the website — a plain request 302s
toward the app/login page, which is why an unauthenticated `requests.get`
against it returns HTML, not JSON. The actual data API lives on a separate
subdomain:

    https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{year}/segments/0/leagues/{leagueId}?view=...

confirmed via a bare `curl` with no cookies returning a clean `401` (a real
auth gate) rather than a redirect or 404.

## Auth

Both leagues are private. `espn_s2` and `SWID` sent as **cookies** (not
headers) on every request authenticate successfully — confirmed by a `200`
with real league data on both leagues using the same credential pair.

## Identity across leagues — resolved

Your ESPN `SWID` (`{E1AB20C5-1EFE-4BF9-9258-...}`) appears verbatim as
`primaryOwner` on your team in **both** leagues — team 25 "Goff Is My
Copilot" in league `1618731`, team 10 "LaPorta Authority" in league
`581297461`. SWID is a reliable, stable "this is you" key across leagues
under the same ESPN account. The open question from before build start is
resolved: no name-matching needed.

## The two leagues are meaningfully different — don't share config

| | League `1618731` | League `581297461` |
|---|---|---|
| Name | "No More Domestic Violence" | "My 2023 League" |
| Teams | 14 (2 divisions: Stars, Stripes) | 12 (no divisions seen) |
| Roster size | 15 (1 QB/2 RB/2 WR/1 TE/1 FLEX/1 D/ST/1 K/**5** BE/1 IR) | 17 (same starters, **7** BE/1 IR) |
| Playoff teams | 8 | not yet checked |
| Playoff seeding rule | `TOTAL_POINTS_SCORED` (not W-L record) | not yet checked |
| Waiver type | Traditional priority, **not FAAB** (`isUsingAcquisitionBudget: false`) | Traditional priority, **not FAAB** |
| Trade veto votes required | 4 | 4 |

**This changes one of your requested features**: neither league uses FAAB
bidding, so there's no budget-ROI number to compute. "Waiver efficiency"
will instead track whether your traditional-priority pickups outscored what
you dropped — the mechanism differs, the underlying question (did this
move help) doesn't.

## Two separate, easy-to-confuse ID namespaces — confirmed empirically, not assumed

ESPN uses two different numbering schemes that look similar but aren't:

- **`defaultPositionId`** (a player's real position) — confirmed by sampling
  real players, not by memory: `1=QB (Lamar Jackson), 2=RB (Saquon Barkley),
  3=WR (Terry McLaurin), 4=TE (Jake Ferguson), 5=K (Tyler Loop), 16=D/ST`.
- **`lineupSlotId`** (a roster slot type) — a different scheme entirely:
  `0=QB, 2=RB, 4=WR, 6=TE, 16=D/ST, 17=K, 20=Bench, 21=IR, 23=FLEX`.

Conflating these two would silently corrupt every lineup-efficiency number
the whole project is built around, so the schema will keep them in clearly
separate, clearly named columns.

## Endpoints confirmed working

| View | Purpose | Status |
|---|---|---|
| `mSettings` | roster slots, scoring rules, schedule/playoff config, waiver/trade settings | Verified, differs per league |
| `mTeam` | team names, `primaryOwner`, `members` (real name + ESPN display name) | Verified |
| `mRoster` | current roster, `lineupSlotId`, injury status, per-player `playerPoolEntry` | Verified |
| `mMatchup` | weekly schedule, `away`/`home` with `totalPoints`, `winner` | Verified — currently `UNDECIDED`, `totalPoints: 0.0` both sides (matchup period 1, `latestScoringPeriod: 1` — the season is at its very start) |
| `mTransactions2` | draft picks, waiver moves, trades — `bidAmount`, `fromTeamId`/`toTeamId`, `type` | Verified — 221 rows already (mostly `DRAFT`) |
| `kona_player_info` | full player pool, `ownership` %, stats, injury status | Verified working, but **only returns 50 players per call** — pagination/filtering (likely ESPN's `X-Fantasy-Filter` header) is unresolved, needed before a full backfill can pull the whole player universe rather than a top-50 slice |

## Open items before schema design

1. Player-pool pagination — needs one more verification pass.
2. League `581297461`'s playoff format (team count, seeding rule) not yet
   checked — don't assume it matches league `1618731`.
3. `scoringItems`' `statId` values (e.g. `53`, `72`, `89`) are ESPN's own
   internal stat codes with no embedded label in the response — will need
   cross-referencing against real player stat lines to confirm what each
   number means, the same way `net_points` was cross-checked against
   reported H2H scores in the FPL project.
