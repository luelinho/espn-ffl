"""Phase 2 — create the database, resolve both leagues' teams to managers.

Scope, per SPEC.md §11 Phase 2 exit criteria: create every table from
db/schema.sql, record each league's own live configuration, and resolve
every team in both leagues to a manager (global identity, keyed by ESPN's
SWID/member GUID — confirmed stable across leagues in Phase 1). Historical
backfill (rosters, matchups, transactions, player stats) is Phase 3.

Every write here is an upsert on a natural key, so running this twice
produces identical state.

Usage:
    python -m src.build_db
"""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timezone

from . import config
from .espn_client import ESPNClient


def connect() -> sqlite3.Connection:
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def apply_schema(conn: sqlite3.Connection) -> None:
    schema_path = config.REPO_ROOT / "db" / "schema.sql"
    conn.executescript(schema_path.read_text())
    conn.commit()


def upsert_league(conn: sqlite3.Connection, league_id: int, name: str, my_team_hint: str) -> None:
    conn.execute(
        """
        INSERT INTO leagues (league_id, name, my_team_hint)
        VALUES (?, ?, ?)
        ON CONFLICT (league_id) DO UPDATE SET
            name = excluded.name, my_team_hint = excluded.my_team_hint
        """,
        (league_id, name, my_team_hint),
    )


def upsert_league_season(conn: sqlite3.Connection, league_id: int, season_year: int, settings: dict, status: dict) -> None:
    schedule = settings.get("scheduleSettings", {})
    acquisition = settings.get("acquisitionSettings", {})
    trade = settings.get("tradeSettings", {})
    scoring = settings.get("scoringSettings", {})
    roster = settings.get("rosterSettings", {})
    conn.execute(
        """
        INSERT INTO league_seasons
            (league_id, season_year, team_count, scoring_type, waiver_type,
             regular_season_weeks, final_week, playoff_team_count, playoff_seeding_rule,
             trade_veto_votes_required, roster_slot_counts_json, scoring_items_json,
             config_json, last_verified)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (league_id, season_year) DO UPDATE SET
            team_count = excluded.team_count,
            scoring_type = excluded.scoring_type,
            waiver_type = excluded.waiver_type,
            regular_season_weeks = excluded.regular_season_weeks,
            final_week = excluded.final_week,
            playoff_team_count = excluded.playoff_team_count,
            playoff_seeding_rule = excluded.playoff_seeding_rule,
            trade_veto_votes_required = excluded.trade_veto_votes_required,
            roster_slot_counts_json = excluded.roster_slot_counts_json,
            scoring_items_json = excluded.scoring_items_json,
            config_json = excluded.config_json,
            last_verified = excluded.last_verified
        """,
        (
            league_id, season_year, settings.get("size"), scoring.get("scoringType"),
            acquisition.get("acquisitionType"),
            schedule.get("matchupPeriodCount"), status.get("finalScoringPeriod"),
            schedule.get("playoffTeamCount"), schedule.get("playoffSeedingRule"),
            trade.get("vetoVotesRequired"),
            json.dumps(roster.get("lineupSlotCounts")), json.dumps(scoring.get("scoringItems")),
            json.dumps(settings), datetime.now(timezone.utc).isoformat(),
        ),
    )


def upsert_manager(conn: sqlite3.Connection, member_id: str, display_name: str, is_owner: bool) -> int:
    conn.execute(
        """
        INSERT INTO managers (espn_member_id, display_name, is_owner)
        VALUES (?, ?, ?)
        ON CONFLICT (espn_member_id) DO UPDATE SET
            display_name = excluded.display_name,
            is_owner = excluded.is_owner OR managers.is_owner
        """,
        (member_id, display_name, int(is_owner)),
    )
    row = conn.execute(
        "SELECT manager_id FROM managers WHERE espn_member_id = ?", (member_id,)
    ).fetchone()
    return row[0]


def upsert_team(conn: sqlite3.Connection, league_id: int, season_year: int, team_id: int,
                 manager_id: int | None, team_name: str, division_id: int | None) -> None:
    conn.execute(
        """
        INSERT INTO teams (league_id, season_year, team_id, manager_id, team_name, division_id)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT (league_id, season_year, team_id) DO UPDATE SET
            manager_id = excluded.manager_id,
            team_name = excluded.team_name,
            division_id = excluded.division_id
        """,
        (league_id, season_year, team_id, manager_id, team_name, division_id),
    )


def log_data_issue(conn: sqlite3.Connection, severity: str, category: str, description: str,
                    league_id: int | None = None) -> None:
    conn.execute(
        """
        INSERT INTO data_issues (detected_at, severity, category, league_id, description)
        VALUES (?, ?, ?, ?, ?)
        """,
        (datetime.now(timezone.utc).isoformat(), severity, category, league_id, description),
    )


def run() -> int:
    print("Phase 2 — schema + league/team resolution")
    print(f"Database: {config.DB_PATH}\n")

    if not config.SEASON_YEAR:
        print("FAILED: SEASON_YEAR not set in .env. Not guessing it.")
        return 1
    if not (config.ESPN_S2 and config.ESPN_SWID):
        print("FAILED: ESPN_S2/ESPN_SWID not set in .env. Both leagues are private.")
        return 1

    conn = connect()
    apply_schema(conn)
    print("Schema applied.")

    client = ESPNClient(archive_dir=config.PHASE1_PAYLOADS, verbose=True)
    total_teams = 0
    total_matched_to_owner = 0

    for league_id, meta in config.LEAGUES.items():
        print(f"\n=== League {league_id} ({meta['my_team_hint']}) ===")
        res = client.get_league(league_id, config.SEASON_YEAR, views=["mSettings", "mTeam"])
        if not res.ok:
            log_data_issue(conn, "error", "league_fetch",
                            f"Could not fetch league {league_id}: {res.summary()}", league_id)
            print(f"  [FAIL] {res.summary()}")
            continue

        body = res.json_body
        settings = body["settings"]
        status = body["status"]
        league_name = settings.get("name", "")

        upsert_league(conn, league_id, league_name, meta["my_team_hint"])
        upsert_league_season(conn, league_id, int(config.SEASON_YEAR), settings, status)
        print(f"  League: {league_name!r} | teams: {settings.get('size')} | "
              f"waiver: {settings.get('acquisitionSettings', {}).get('acquisitionType')} | "
              f"playoff teams: {settings.get('scheduleSettings', {}).get('playoffTeamCount')}")

        members_by_id = {m["id"]: m for m in body.get("members", [])}

        teams = body.get("teams", [])
        if len(teams) != settings.get("size"):
            log_data_issue(conn, "warning", "team_count_mismatch",
                            f"League {league_id}: settings.size={settings.get('size')} but "
                            f"{len(teams)} team objects returned.", league_id)

        found_owner_here = False
        for t in teams:
            member_id = t.get("primaryOwner")
            member = members_by_id.get(member_id, {})
            display_name = member.get("displayName") or f"{member.get('firstName', '')} {member.get('lastName', '')}".strip()
            is_owner = member_id == config.ESPN_SWID
            if is_owner:
                found_owner_here = True
                total_matched_to_owner += 1

            manager_id = upsert_manager(conn, member_id, display_name or None, is_owner) if member_id else None
            team_name = t.get("name", "")
            upsert_team(conn, league_id, int(config.SEASON_YEAR), t["id"], manager_id, team_name, t.get("divisionId"))
            total_teams += 1
            tag = "  <- YOU" if is_owner else ""
            print(f"    team {t['id']:>3}  {team_name!r:40} owner={display_name}{tag}")

        if not found_owner_here:
            log_data_issue(conn, "error", "owner_not_found",
                            f"League {league_id}: no team's primaryOwner matched the configured SWID.",
                            league_id)
            print(f"  !! Could not find your team in league {league_id} — SWID matched nothing.")

        conn.commit()

    conn.execute(
        """
        INSERT INTO ingest_runs (started_at, finished_at, job_name, status, requests_made, rows_written)
        VALUES (?, ?, 'phase2_build_db', ?, ?, ?)
        """,
        (
            datetime.now(timezone.utc).isoformat(),
            datetime.now(timezone.utc).isoformat(),
            "success" if total_matched_to_owner == len(config.LEAGUES) else "partial",
            client.request_count,
            total_teams,
        ),
    )
    conn.commit()

    print(f"\n{total_teams} teams stored across {len(config.LEAGUES)} leagues.")
    print(f"Your team matched by SWID in {total_matched_to_owner}/{len(config.LEAGUES)} leagues.")
    if total_matched_to_owner != len(config.LEAGUES):
        print("WARNING: expected to find your team in every configured league — check data_issues.")

    conn.close()
    print("\nPhase 2 complete." if total_matched_to_owner == len(config.LEAGUES)
          else "\nPhase 2 complete, with issues logged to data_issues.")
    return 0


if __name__ == "__main__":
    sys.exit(run())
