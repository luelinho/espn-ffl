"""Phase 4 — the one daily job. Idempotent, safe to run repeatedly.

Unlike backfill.py's unconditional refetch, this skips a week entirely
once it's fully final in our own storage (raw_team_week.is_final = 1 for
every team) — cheaper, and matches the FPL project's daily_sync pattern of
not re-touching settled history. The current (live) week and any week that
isn't yet marked final are always refetched, since a live week's scores
change as games are played.

Usage:
    python -m src.daily_sync
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone

from . import config, ingest
from .espn_client import ESPNClient


def week_is_fully_final(conn, league_id: int, season_year: str, week: int, team_count: int) -> bool:
    row = conn.execute(
        "SELECT COUNT(*) FROM raw_team_week WHERE league_id=? AND season_year=? AND week=? AND is_final=1",
        (league_id, int(season_year), week),
    ).fetchone()
    return row[0] == team_count


def run() -> int:
    started = datetime.now(timezone.utc).isoformat()
    print("Phase 4 — daily sync\n")

    if not (config.ESPN_S2 and config.ESPN_SWID and config.SEASON_YEAR):
        print("FAILED: .env is missing ESPN_S2 / ESPN_SWID / SEASON_YEAR.")
        return 1

    conn = ingest.connect()
    client = ESPNClient(archive_dir=config.PHASE1_PAYLOADS, verbose=True)

    weeks_touched = 0
    weeks_skipped = 0
    current_weeks_seen: set[int] = set()

    for league_id in config.LEAGUES:
        res = client.get_league(league_id, config.SEASON_YEAR, views=["mSettings"])
        if not res.ok:
            print(f"League {league_id}: FAILED to fetch settings — {res.summary()}")
            continue
        current_matchup_period = res.json_body["status"]["currentMatchupPeriod"]
        team_count = res.json_body["settings"]["size"]
        current_weeks_seen.add(current_matchup_period)
        print(f"=== League {league_id} — current matchup period: {current_matchup_period} ===")

        for week in range(1, current_matchup_period + 1):
            if week < current_matchup_period and week_is_fully_final(conn, league_id, config.SEASON_YEAR, week, team_count):
                print(f"  week {week}: already final, skipped")
                weeks_skipped += 1
                continue
            ok = ingest.load_week(conn, client, league_id, config.SEASON_YEAR, week)
            print(f"  week {week}: {'refreshed' if ok else 'FAILED'}")
            weeks_touched += 1

        n_tx = ingest.load_transactions(conn, client, league_id, config.SEASON_YEAR)
        n_standings = ingest.load_standings(conn, client, league_id, config.SEASON_YEAR, current_matchup_period)
        print(f"  transactions: {n_tx} rows | standings: {n_standings} teams")
        print()

    # Real NFL game status — universal, not per-league, so fetched once per
    # distinct current week (usually just one) rather than once per league.
    for week in current_weeks_seen:
        n_games = ingest.load_pro_games(conn, client, config.SEASON_YEAR, week)
        print(f"Real NFL games, week {week}: {n_games} games (status refreshed)")

    unresolved = conn.execute(
        "SELECT COUNT(*) FROM data_issues WHERE resolved = 0 AND detected_at > ?", (started,)
    ).fetchone()[0]

    conn.execute(
        """
        INSERT INTO ingest_runs (started_at, finished_at, job_name, status, requests_made, rows_written)
        VALUES (?, ?, 'daily_sync', 'success', ?, ?)
        """,
        (started, datetime.now(timezone.utc).isoformat(), client.request_count, weeks_touched),
    )
    conn.commit()
    conn.close()

    print(f"Weeks touched: {weeks_touched} | weeks skipped (already final): {weeks_skipped}")
    print(f"New data_issues this run: {unresolved}")
    print(f"Total requests made: {client.request_count}")
    print("\nDaily sync complete.")
    return 0


if __name__ == "__main__":
    sys.exit(run())
