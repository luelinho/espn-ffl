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
| Luck, all-play, expected wins, power rankings | 5 (placeholder) | **Withhold** |
| Playoff odds | 7 (placeholder) | **Withhold** |

**These thresholds are placeholders, not the owner's decision yet** — see
SPEC.md §13. Confirm with the owner before Phase 5 closes; don't treat them
as settled until then. Below the threshold, say "insufficient sample — N
weeks, need M." Do not show the number with a caveat attached.

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
  bench); playoff format not yet verified — do not assume it matches
  league `1618731`
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

Not yet built — Phase 7. When it exists: a single self-contained HTML file
(data baked in, no server), with a league switcher since every page needs
to know which of the two leagues it's showing. Fresh visual identity for
this project, not a reskin of the FPL dashboard (owner's explicit call,
2026-09-13).
