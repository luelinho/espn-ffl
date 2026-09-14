"""Phase 6 — weekly recap generator (SPEC.md §5 Tier 1).

Generates reports/week{N}_{league_id}.md for every FINALIZED week — same
gate as FPL's recap.py only running for data-checked gameweeks. A week
isn't final here until every game feeding it is over (raw_team_week.is_final
= 1 for every team), so a genuinely live week correctly produces nothing
yet rather than a recap built on scores that are still changing.

Usage:
    python -m src.recap
"""

from __future__ import annotations

import sys

from . import config
from .ingest import connect


def finalized_weeks(conn, league_id: int, season_year: int) -> list[int]:
    rows = conn.execute(
        """
        SELECT week FROM raw_team_week
        WHERE league_id = ? AND season_year = ?
        GROUP BY week
        HAVING MIN(is_final) = 1
        ORDER BY week
        """,
        (league_id, season_year),
    ).fetchall()
    return [w for (w,) in rows]


def team_label(conn, league_id: int, season_year: int, team_id: int) -> str:
    row = conn.execute(
        """
        SELECT t.team_name, m.display_name FROM teams t
        LEFT JOIN managers m ON m.manager_id = t.manager_id
        WHERE t.league_id=? AND t.season_year=? AND t.team_id=?
        """,
        (league_id, season_year, team_id),
    ).fetchone()
    if not row:
        return f"team {team_id}"
    name, manager = row
    return f"{name} ({manager})" if manager else name


def generate_week_recap(conn, league_id: int, season_year: int, week: int) -> str:
    L = []
    A = L.append
    league_name = conn.execute("SELECT name FROM leagues WHERE league_id=?", (league_id,)).fetchone()[0]
    A(f"# {league_name} — Week {week} Recap")
    A("")
    A("*Fact = stored raw data. Computed = derived by a documented formula. See CLAUDE.md.*")
    A("")

    scores = conn.execute(
        "SELECT team_id, total_points FROM raw_team_week WHERE league_id=? AND season_year=? AND week=? ORDER BY total_points DESC",
        (league_id, season_year, week),
    ).fetchall()
    if not scores:
        A("*No data for this week.*")
        return "\n".join(L) + "\n"

    winner_id, winner_pts = scores[0]
    loser_id, loser_pts = scores[-1]
    A(f"**Week high (Fact):** {team_label(conn, league_id, season_year, winner_id)} — {winner_pts} points, best in the league this week.")
    A(f"**Week low (Fact):** {team_label(conn, league_id, season_year, loser_id)} — {loser_pts} points, last in the league this week.")
    A("")

    matchups = conn.execute(
        "SELECT team_a, team_b, score_a, score_b, winner FROM raw_matchups WHERE league_id=? AND season_year=? AND week=? AND status='final'",
        (league_id, season_year, week),
    ).fetchall()
    if matchups:
        blowout = max(matchups, key=lambda m: abs((m[2] or 0) - (m[3] or 0)))
        closest = min(matchups, key=lambda m: abs((m[2] or 0) - (m[3] or 0)))
        a_lbl, b_lbl = team_label(conn, league_id, season_year, blowout[0]), team_label(conn, league_id, season_year, blowout[1])
        A(f"**Biggest blowout (Fact):** {a_lbl} {blowout[2]} - {blowout[3]} {b_lbl} — margin {abs(blowout[2]-blowout[3]):.1f}.")
        a_lbl, b_lbl = team_label(conn, league_id, season_year, closest[0]), team_label(conn, league_id, season_year, closest[1])
        A(f"**Closest margin (Fact):** {a_lbl} {closest[2]} - {closest[3]} {b_lbl} — margin {abs(closest[2]-closest[3]):.1f}.")
        A("")

    eff_rows = conn.execute(
        "SELECT team_id, lineup_efficiency, bench_points FROM derived_team_week WHERE league_id=? AND season_year=? AND week=? ORDER BY lineup_efficiency DESC",
        (league_id, season_year, week),
    ).fetchall()
    if eff_rows:
        best = eff_rows[0]
        worst = eff_rows[-1]
        A(f"**Best lineup-setting (Computed):** {team_label(conn, league_id, season_year, best[0])} — {best[1]*100:.1f}% efficiency.")
        A(f"**Most points left on the bench (Computed):** {team_label(conn, league_id, season_year, worst[0])} — {worst[2]:.1f} bench points.")

    return "\n".join(L) + "\n"


def run() -> int:
    print("Phase 6 — recap generation\n")
    conn = connect()
    config.REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    total = 0
    for league_id in config.LEAGUES:
        weeks = finalized_weeks(conn, league_id, int(config.SEASON_YEAR))
        if not weeks:
            print(f"League {league_id}: no finalized weeks yet — nothing to generate (correct, Week 1 is still live).")
            continue
        for week in weeks:
            content = generate_week_recap(conn, league_id, int(config.SEASON_YEAR), week)
            out_path = config.REPORTS_DIR / f"week{week}_{league_id}.md"
            out_path.write_text(content)
            print(f"  Wrote {out_path}")
            total += 1

    conn.close()
    print(f"\nRecap generation complete. {total} report(s) written.")
    return 0


if __name__ == "__main__":
    sys.exit(run())
