"""Phase 3 — unconditional historical backfill for both leagues.

Ingests every week from 1 through the current matchup period (inclusive —
the current week is captured provisionally, same idea as an FPL provisional
gameweek), plus reference data (real NFL teams), transactions, and a
standings snapshot.

Usage:
    python -m src.backfill
"""

from __future__ import annotations

import sys

from . import config, ingest
from .espn_client import ESPNClient


def run() -> int:
    print("Phase 3 — historical backfill\n")
    conn = ingest.connect()
    client = ESPNClient(archive_dir=config.PHASE1_PAYLOADS, verbose=True)

    if not (config.ESPN_S2 and config.ESPN_SWID and config.SEASON_YEAR):
        print("FAILED: .env is missing ESPN_S2 / ESPN_SWID / SEASON_YEAR.")
        return 1

    n_pro_teams = ingest.load_pro_teams(conn, client, config.SEASON_YEAR)
    print(f"Reference data: {n_pro_teams} real NFL teams.\n")

    for league_id in config.LEAGUES:
        res = client.get_league(league_id, config.SEASON_YEAR, views=["mSettings"])
        if not res.ok:
            print(f"League {league_id}: FAILED to fetch settings — {res.summary()}")
            continue
        current_matchup_period = res.json_body["status"]["currentMatchupPeriod"]
        print(f"=== League {league_id} — current matchup period: {current_matchup_period} ===")

        for week in range(1, current_matchup_period + 1):
            ok = ingest.load_week(conn, client, league_id, config.SEASON_YEAR, week)
            label = "provisional" if week == current_matchup_period else "final"
            print(f"  week {week}: {'OK' if ok else 'FAILED'} ({label} expected)")

        n_tx = ingest.load_transactions(conn, client, league_id, config.SEASON_YEAR)
        print(f"  transactions: {n_tx} rows")

        n_standings = ingest.load_standings(conn, client, league_id, config.SEASON_YEAR, current_matchup_period)
        print(f"  standings snapshot (week {current_matchup_period}): {n_standings} teams")

        n_games = ingest.load_pro_games(conn, client, config.SEASON_YEAR, current_matchup_period)
        print(f"  real NFL games, week {current_matchup_period}: {n_games} games")
        print()

    # Validators
    print("Validators:")
    problems = []
    for league_id in config.LEAGUES:
        team_count = conn.execute(
            "SELECT COUNT(*) FROM teams WHERE league_id = ? AND season_year = ?",
            (league_id, int(config.SEASON_YEAR)),
        ).fetchone()[0]
        expected = conn.execute(
            "SELECT team_count FROM league_seasons WHERE league_id = ? AND season_year = ?",
            (league_id, int(config.SEASON_YEAR)),
        ).fetchone()
        if expected and team_count != expected[0]:
            problems.append(f"League {league_id}: {team_count} teams stored, expected {expected[0]}")

        roster_weeks = conn.execute(
            "SELECT DISTINCT week FROM raw_roster_entries WHERE league_id = ? AND season_year = ? ORDER BY week",
            (league_id, int(config.SEASON_YEAR)),
        ).fetchall()
        print(f"  League {league_id}: roster data for weeks {[w[0] for w in roster_weeks]}")

    unresolved_issues = conn.execute(
        "SELECT severity, category, description FROM data_issues WHERE resolved = 0"
    ).fetchall()
    if unresolved_issues:
        print(f"\n{len(unresolved_issues)} data_issues logged:")
        for sev, cat, desc in unresolved_issues:
            print(f"  [{sev}] {cat}: {desc}")
    else:
        print("\nNo data_issues logged.")

    if problems:
        for p in problems:
            print(f"  PROBLEM: {p}")

    conn.close()
    print(f"\nTotal requests made: {client.request_count}")
    print("Phase 3 backfill complete." if not problems else "Phase 3 backfill complete, with problems above.")
    return 0


if __name__ == "__main__":
    sys.exit(run())
