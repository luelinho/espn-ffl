"""Phase 6 — proves every query in queries/*.sql actually runs against live
data, with real parameters. Not part of the daily pipeline; a standalone
check so the library stays provably working as the schema evolves.

Usage:
    python -m src.vet_queries
"""

from __future__ import annotations

import sys

from . import config
from .ingest import connect

LEAGUE_1, LEAGUE_2 = list(config.LEAGUES.keys())


def owner_team_id(conn, league_id: int) -> int:
    row = conn.execute(
        "SELECT t.team_id FROM teams t JOIN managers m ON m.manager_id = t.manager_id "
        "WHERE t.league_id = ? AND t.season_year = ? AND m.is_owner = 1",
        (league_id, int(config.SEASON_YEAR)),
    ).fetchone()
    return row[0]


def any_two_team_ids(conn, league_id: int) -> tuple[int, int]:
    rows = conn.execute(
        "SELECT team_id FROM teams WHERE league_id = ? AND season_year = ? LIMIT 2",
        (league_id, int(config.SEASON_YEAR)),
    ).fetchall()
    return rows[0][0], rows[1][0]


def run() -> int:
    print("Phase 6 — vetting queries/*.sql against live data\n")
    conn = connect()
    my_team_1 = owner_team_id(conn, LEAGUE_1)
    team_a, team_b = any_two_team_ids(conn, LEAGUE_1)

    checks = [
        ("roster_by_week.sql", {"league_id": LEAGUE_1, "season_year": int(config.SEASON_YEAR), "team_id": my_team_1, "week": 1}),
        ("standings_at_week.sql", {"league_id": LEAGUE_1, "season_year": int(config.SEASON_YEAR), "week": 1}),
        ("lineup_efficiency_summary.sql", {"league_id": LEAGUE_1, "season_year": int(config.SEASON_YEAR), "through_week": 1}),
        ("week_extremes.sql", {"league_id": LEAGUE_1, "season_year": int(config.SEASON_YEAR), "week": 1}),
        ("matchup_history.sql", {"league_id": LEAGUE_1, "season_year": int(config.SEASON_YEAR), "team_a": team_a, "team_b": team_b}),
        ("waiver_moves_summary.sql", {"league_id": LEAGUE_1, "season_year": int(config.SEASON_YEAR), "team_id": my_team_1}),
        ("open_data_issues.sql", {"league_id": None}),
        ("gate_status.sql", {"league_id": LEAGUE_1, "season_year": int(config.SEASON_YEAR), "team_id": my_team_1, "through_week": 1}),
    ]

    ok = True
    for filename, params in checks:
        sql = (config.REPO_ROOT / "queries" / filename).read_text()
        try:
            rows = conn.execute(sql, params).fetchall()
            print(f"  [OK  ] {filename}: {len(rows)} rows")
        except Exception as exc:  # noqa: BLE001 — a vet script should report, not crash
            print(f"  [FAIL] {filename}: {exc}")
            ok = False

    conn.close()
    print("\nAll queries vetted successfully." if ok else "\nSome queries FAILED — see above.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(run())
