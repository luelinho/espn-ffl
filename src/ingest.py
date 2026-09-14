"""Shared ingestion loaders — used by both backfill.py (Phase 3, unconditional)
and the future daily_sync.py (Phase 4, skips already-final weeks).

Key discovery this phase (2026-09-13, real data, League 1618731 Week 1):
ESPN's own `mMatchup.totalPoints` for a team can lag behind what the
per-player roster stats already show — observed live: totalPoints=0.0 while
summing that team's starters' actual week-1 appliedTotal gives 137.0, with
real per-player stats populated (Chase Brown 18, D'Andre Swift 33, etc, all
round numbers consistent with completed games, not projections). Same shape
of bug as the FPL project's entry_history.points lag, same fix: a team's
week total is computed from the more current, granular roster data, not
trusted blindly from the coarser matchup summary field. See SPEC.md §2
Fallback.

A week is `is_final` once ESPN's own `status.currentMatchupPeriod` has moved
past it — i.e. ESPN itself is no longer treating it as the active week.
Before that, everything captured is provisional (is_final=0), upserted on
every run, same "upsert until final" pattern as the FPL project.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from . import config
from .espn_client import ESPNClient


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def log_issue(conn: sqlite3.Connection, severity: str, category: str, description: str,
              league_id: Optional[int] = None, season_year: Optional[int] = None,
              week: Optional[int] = None, team_id: Optional[int] = None) -> None:
    conn.execute(
        """
        INSERT INTO data_issues (detected_at, severity, category, league_id, season_year, week, team_id, description)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (now(), severity, category, league_id, season_year, week, team_id, description),
    )


# --- reference: real NFL teams ------------------------------------------------

def load_pro_teams(conn: sqlite3.Connection, client: ESPNClient, season_year: str) -> int:
    res = client.get_season_reference(season_year, views=["proTeamSchedules"])
    if not res.ok:
        log_issue(conn, "error", "pro_teams_fetch", f"proTeamSchedules failed: {res.summary()}")
        return 0
    teams = res.json_body.get("settings", {}).get("proTeams", [])
    for t in teams:
        conn.execute(
            """
            INSERT INTO pro_teams (pro_team_id, season_year, name, abbrev)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (pro_team_id, season_year) DO UPDATE SET
                name = excluded.name, abbrev = excluded.abbrev
            """,
            (t["id"], int(season_year), t.get("name", ""), t.get("abbrev", "")),
        )
    conn.commit()
    return len(teams)


# --- per-week extraction helpers ---------------------------------------------

def _actual_week_stat(stats: list[dict], week: int) -> Optional[dict]:
    """The one stats-array entry that is this week's real (not projected)
    total: statSourceId 0 = actual, statSplitTypeId 1 = single week."""
    for s in stats:
        if s.get("scoringPeriodId") == week and s.get("statSourceId") == 0 and s.get("statSplitTypeId") == 1:
            return s
    return None


BENCH_SLOTS = {20, 21}  # Bench, IR — confirmed Phase 1


def load_week(conn: sqlite3.Connection, client: ESPNClient, league_id: int, season_year: str, week: int) -> bool:
    """Captures one week's rosters, computed team totals, and matchups for
    one league. Returns True on success. Safe to call repeatedly — every
    write is upsert-until-final."""
    res = client.get_league(league_id, season_year, views=["mRoster", "mTeam", "mMatchup"])
    if not res.ok:
        log_issue(conn, "error", "week_fetch", f"League {league_id} week {week}: {res.summary()}",
                   league_id, int(season_year), week)
        return False

    body = res.json_body
    current_matchup_period = body["status"]["currentMatchupPeriod"]
    is_final = current_matchup_period > week

    computed_team_points: dict[int, float] = {}

    for t in body.get("teams", []):
        team_id = t["id"]
        team_total = 0.0
        for entry in t.get("roster", {}).get("entries", []):
            player = entry["playerPoolEntry"]["player"]
            player_id = player["id"]

            conn.execute(
                """
                INSERT INTO players (player_id, full_name, default_position_id, pro_team_id)
                VALUES (?, ?, ?, ?)
                ON CONFLICT (player_id) DO UPDATE SET
                    full_name = excluded.full_name,
                    default_position_id = excluded.default_position_id,
                    pro_team_id = excluded.pro_team_id
                """,
                (player_id, player.get("fullName", ""), player.get("defaultPositionId"), player.get("proTeamId")),
            )

            wk_stat = _actual_week_stat(player.get("stats", []), week)
            points = wk_stat.get("appliedTotal") if wk_stat else None
            is_starter = entry["lineupSlotId"] not in BENCH_SLOTS

            if wk_stat is not None:
                conn.execute(
                    """
                    INSERT INTO raw_player_week_stats (season_year, week, player_id, stats_json, is_final, source, fetched_at)
                    VALUES (?, ?, ?, ?, ?, 'espn_roster_entry', ?)
                    ON CONFLICT (season_year, week, player_id) DO UPDATE SET
                        stats_json = excluded.stats_json, is_final = excluded.is_final, fetched_at = excluded.fetched_at
                    WHERE raw_player_week_stats.is_final = 0
                    """,
                    (int(season_year), week, player_id, json.dumps(wk_stat.get("stats", {})), int(is_final), now()),
                )

            conn.execute(
                """
                INSERT INTO raw_roster_entries
                    (league_id, season_year, week, team_id, player_id, lineup_slot_id, is_starter, points_scored, is_final, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (league_id, season_year, week, team_id, player_id) DO UPDATE SET
                    lineup_slot_id = excluded.lineup_slot_id, is_starter = excluded.is_starter,
                    points_scored = excluded.points_scored, is_final = excluded.is_final, fetched_at = excluded.fetched_at
                WHERE raw_roster_entries.is_final = 0
                """,
                (league_id, int(season_year), week, team_id, player_id, entry["lineupSlotId"],
                 int(is_starter), points, int(is_final), now()),
            )

            if is_starter and points is not None:
                team_total += points

        computed_team_points[team_id] = round(team_total, 2)

        conn.execute(
            """
            INSERT INTO raw_team_week (league_id, season_year, week, team_id, total_points, is_final, source, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, 'computed_from_roster', ?)
            ON CONFLICT (league_id, season_year, week, team_id) DO UPDATE SET
                total_points = excluded.total_points, is_final = excluded.is_final, fetched_at = excluded.fetched_at
            WHERE raw_team_week.is_final = 0
            """,
            (league_id, int(season_year), week, team_id, computed_team_points[team_id], int(is_final), now()),
        )

    # Matchups + cross-check against ESPN's own reported totalPoints.
    for m in body.get("schedule", []):
        if m.get("matchupPeriodId") != week:
            continue
        home, away = m.get("home"), m.get("away")
        if not home or not away:
            continue  # a bye — real, not an error

        for side in (home, away):
            espn_total = side.get("totalPoints", 0.0)
            our_total = computed_team_points.get(side["teamId"], 0.0)
            # `if espn_total` would treat 0.0 as falsy and skip exactly the
            # case this check exists for (ESPN's own field stuck at 0 while
            # real per-player stats already show real points) — use
            # `is not None` instead. Found live, 2026-09-13: League 1618731
            # team 25 was ESPN-reported 0.0 vs. our computed 137.0.
            if espn_total is not None and abs(espn_total - our_total) > 0.05:
                log_issue(conn, "warning", "team_total_mismatch",
                          f"League {league_id} week {week} team {side['teamId']}: "
                          f"ESPN mMatchup.totalPoints={espn_total} vs. summed roster points={our_total}",
                          league_id, int(season_year), week, side["teamId"])

        conn.execute(
            """
            INSERT INTO raw_matchups (league_id, season_year, week, team_a, team_b, score_a, score_b, winner, status, source, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'espn_mMatchup', ?)
            ON CONFLICT (league_id, season_year, week, team_a, team_b) DO UPDATE SET
                score_a = excluded.score_a, score_b = excluded.score_b,
                winner = excluded.winner, status = excluded.status, fetched_at = excluded.fetched_at
            WHERE raw_matchups.status != 'final'
            """,
            (league_id, int(season_year), week, home["teamId"], away["teamId"],
             computed_team_points.get(home["teamId"]), computed_team_points.get(away["teamId"]),
             m.get("winner"), "final" if is_final else "provisional", now()),
        )

    conn.commit()
    return True


def load_transactions(conn: sqlite3.Connection, client: ESPNClient, league_id: int, season_year: str) -> int:
    res = client.get_league(league_id, season_year, views=["mTransactions2"])
    if not res.ok:
        log_issue(conn, "error", "transactions_fetch", f"League {league_id}: {res.summary()}", league_id)
        return 0

    rows = res.json_body.get("transactions", [])
    for tx in rows:
        conn.execute(
            """
            INSERT INTO raw_transactions (transaction_id, league_id, season_year, week, team_id, type, bid_amount, status, proposed_at, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (transaction_id) DO UPDATE SET
                status = excluded.status, fetched_at = excluded.fetched_at
            """,
            (tx["id"], league_id, int(season_year), tx.get("scoringPeriodId"), tx.get("teamId"),
             tx.get("type"), tx.get("bidAmount"), tx.get("status"),
             datetime.fromtimestamp(tx["proposedDate"] / 1000, tz=timezone.utc).isoformat() if tx.get("proposedDate") else None,
             now()),
        )
        for item in tx.get("items", []):
            conn.execute(
                """
                INSERT INTO raw_transaction_items (transaction_id, player_id, from_team_id, to_team_id, item_type)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT (transaction_id, player_id) DO UPDATE SET
                    from_team_id = excluded.from_team_id, to_team_id = excluded.to_team_id, item_type = excluded.item_type
                """,
                (tx["id"], item.get("playerId"), item.get("fromTeamId"), item.get("toTeamId"), item.get("type")),
            )
    conn.commit()
    return len(rows)


def load_standings(conn: sqlite3.Connection, client: ESPNClient, league_id: int, season_year: str, week: int) -> int:
    res = client.get_league(league_id, season_year, views=["mTeam"])
    if not res.ok:
        log_issue(conn, "error", "standings_fetch", f"League {league_id}: {res.summary()}", league_id)
        return 0
    n = 0
    for t in res.json_body.get("teams", []):
        record = t.get("record", {}).get("overall", {})
        conn.execute(
            """
            INSERT INTO standings_snapshots (league_id, season_year, week, team_id, wins, losses, ties, points_for, points_against, playoff_seed, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (league_id, season_year, week, team_id) DO UPDATE SET
                wins = excluded.wins, losses = excluded.losses, ties = excluded.ties,
                points_for = excluded.points_for, points_against = excluded.points_against,
                playoff_seed = excluded.playoff_seed, created_at = excluded.created_at
            """,
            (league_id, int(season_year), week, t["id"],
             record.get("wins", 0), record.get("losses", 0), record.get("ties", 0),
             record.get("pointsFor", 0.0), record.get("pointsAgainst", 0.0),
             t.get("playoffSeed"), now()),
        )
        n += 1
    conn.commit()
    return n
