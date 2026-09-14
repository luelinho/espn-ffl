"""Phase 5 — Tier 0-2 analytics: ledger, lineup efficiency, waiver/trade value.

Optimal lineup is computed exactly (not approximated) via a bitmask DP over
which players fill which starting slot instances, using each player's real
`eligible_slots_json` (captured from ESPN, not a hand-guessed position->slot
map — real data showed eligibility is broader than the naive mapping, e.g.
a WR's eligibleSlots includes slot 3, not just 4/23). Roster sizes here
(≤17 players, ≤10 starting-slot instances) keep this fast — reachable
DP states are bounded by C(roster_size, starting_slots), a few thousand at
most, not 2^17.

Tier 3 columns (allplay, expected_wins, luck_index) are left NULL below the
weeks_played gate (5, owner-confirmed) — not computed-but-hidden, genuinely
not computed yet, since there's no value in running a "luck" calculation
against a 1-week sample before the gate ever opens.

Usage:
    python -m src.calculate
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone

from . import config
from .ingest import connect, BENCH_SLOTS

CALC_VERSION = "v1"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def optimal_lineup_points(players: list[tuple[int, float, list[int]]], slot_counts: dict[int, int]) -> float:
    """players: (player_id, points, eligible_slot_ids). Exact max-weight
    assignment via bitmask DP over slot instances."""
    slot_instances = []
    for slot_id, count in slot_counts.items():
        if slot_id in BENCH_SLOTS or count <= 0:
            continue
        slot_instances.extend([slot_id] * count)

    dp = {0: 0.0}
    for slot_id in slot_instances:
        new_dp = dict(dp)  # option: this slot goes unfilled (roster too thin)
        for mask, score in dp.items():
            for i, (_, pts, elig) in enumerate(players):
                bit = 1 << i
                if mask & bit or slot_id not in elig:
                    continue
                nm = mask | bit
                val = score + pts
                if new_dp.get(nm, float("-inf")) < val:
                    new_dp[nm] = val
        dp = new_dp
    return max(dp.values()) if dp else 0.0


def calc_team_week(conn, league_id: int, season_year: int, week: int, team_id: int,
                    slot_counts: dict[int, int]) -> None:
    rows = conn.execute(
        """
        SELECT r.player_id, r.points_scored, r.is_starter, p.eligible_slots_json
        FROM raw_roster_entries r JOIN players p ON p.player_id = r.player_id
        WHERE r.league_id=? AND r.season_year=? AND r.week=? AND r.team_id=?
        """,
        (league_id, season_year, week, team_id),
    ).fetchall()
    if not rows:
        return

    actual_starter_points = sum(pts for _, pts, starter, _ in rows if starter and pts is not None)
    bench_points = sum(pts for _, pts, starter, _ in rows if not starter and pts is not None)

    players = [
        (pid, pts, json.loads(elig_json or "[]"))
        for pid, pts, _, elig_json in rows if pts is not None
    ]
    optimal = optimal_lineup_points(players, slot_counts)
    efficiency = (actual_starter_points / optimal) if optimal else None

    conn.execute(
        """
        INSERT INTO derived_team_week
            (league_id, season_year, week, team_id, actual_starter_points, optimal_lineup_points,
             lineup_efficiency, bench_points, score_rank, calc_version, calculated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
        ON CONFLICT (league_id, season_year, week, team_id) DO UPDATE SET
            actual_starter_points = excluded.actual_starter_points,
            optimal_lineup_points = excluded.optimal_lineup_points,
            lineup_efficiency = excluded.lineup_efficiency,
            bench_points = excluded.bench_points,
            calc_version = excluded.calc_version,
            calculated_at = excluded.calculated_at
        """,
        (league_id, season_year, week, team_id, actual_starter_points, optimal,
         efficiency, bench_points, CALC_VERSION, now()),
    )


def backfill_score_ranks(conn, league_id: int, season_year: int, week: int) -> None:
    rows = conn.execute(
        "SELECT team_id, actual_starter_points FROM derived_team_week WHERE league_id=? AND season_year=? AND week=? ORDER BY actual_starter_points DESC",
        (league_id, season_year, week),
    ).fetchall()
    for rank, (team_id, _) in enumerate(rows, start=1):
        conn.execute(
            "UPDATE derived_team_week SET score_rank=? WHERE league_id=? AND season_year=? AND week=? AND team_id=?",
            (rank, league_id, season_year, week, team_id),
        )


def calc_team_season(conn, league_id: int, season_year: int, through_week: int, team_id: int) -> None:
    # Win/loss/tie record comes from ESPN's own standings snapshot — that's
    # genuinely decided-results-only and not subject to the live-week lag.
    # points_for/points_against are NOT: standings_snapshots.points_for is
    # sourced from ESPN's record.overall.pointsFor, which lags exactly like
    # mMatchup.totalPoints did (confirmed live, same bug — team 25 showed
    # points_for=0.0 in standings_snapshots while raw_team_week.total_points
    # already had 137.0). So points_for/against are computed from our own
    # already-correct raw_team_week/raw_matchups instead of trusted from ESPN.
    standing = conn.execute(
        "SELECT wins, losses, ties FROM standings_snapshots WHERE league_id=? AND season_year=? AND week=? AND team_id=?",
        (league_id, season_year, through_week, team_id),
    ).fetchone()
    w, l, t = standing if standing else (0, 0, 0)

    pf = conn.execute(
        "SELECT COALESCE(SUM(total_points), 0) FROM raw_team_week WHERE league_id=? AND season_year=? AND team_id=? AND week<=?",
        (league_id, season_year, team_id, through_week),
    ).fetchone()[0]
    pa = conn.execute(
        """
        SELECT COALESCE(SUM(opp.total_points), 0)
        FROM raw_matchups m
        JOIN raw_team_week opp ON opp.league_id=m.league_id AND opp.season_year=m.season_year AND opp.week=m.week
            AND opp.team_id = CASE WHEN m.team_a = ? THEN m.team_b ELSE m.team_a END
        WHERE m.league_id=? AND m.season_year=? AND m.week<=? AND (m.team_a=? OR m.team_b=?)
        """,
        (team_id, league_id, season_year, through_week, team_id, team_id),
    ).fetchone()[0]

    weekly = conn.execute(
        "SELECT lineup_efficiency, bench_points FROM derived_team_week WHERE league_id=? AND season_year=? AND team_id=? AND week<=?",
        (league_id, season_year, team_id, through_week),
    ).fetchall()
    weeks_played = len(weekly)
    effs = [e for e, _ in weekly if e is not None]
    season_eff = sum(effs) / len(effs) if effs else None
    total_bench = sum(b for _, b in weekly if b is not None)
    avg_pf = pf / weeks_played if weeks_played else None
    avg_pa = pa / weeks_played if weeks_played else None
    is_provisional = weeks_played < config.GATE_LUCK_METRICS

    conn.execute(
        """
        INSERT INTO derived_team_season
            (league_id, season_year, team_id, through_week, weeks_played, points_for, points_against,
             avg_pf, avg_pa, actual_w, actual_l, actual_t, season_lineup_efficiency, total_bench_points,
             is_provisional, calc_version, calculated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (league_id, season_year, team_id, through_week) DO UPDATE SET
            weeks_played = excluded.weeks_played, points_for = excluded.points_for,
            points_against = excluded.points_against, avg_pf = excluded.avg_pf, avg_pa = excluded.avg_pa,
            actual_w = excluded.actual_w, actual_l = excluded.actual_l, actual_t = excluded.actual_t,
            season_lineup_efficiency = excluded.season_lineup_efficiency,
            total_bench_points = excluded.total_bench_points, is_provisional = excluded.is_provisional,
            calc_version = excluded.calc_version, calculated_at = excluded.calculated_at
        """,
        (league_id, season_year, team_id, through_week, weeks_played, pf, pa, avg_pf, avg_pa,
         w, l, t, season_eff, total_bench, int(is_provisional), CALC_VERSION, now()),
    )


def calc_waiver_moves(conn, league_id: int, season_year: int, latest_week: int) -> int:
    horizon = config.WAIVER_TRADE_ROI_HORIZON_WEEKS
    txs = conn.execute(
        """
        SELECT transaction_id, week FROM raw_transactions
        WHERE league_id=? AND season_year=? AND type IN ('WAIVER','FREEAGENT') AND status='EXECUTED'
        """,
        (league_id, season_year),
    ).fetchall()

    n = 0
    for tx_id, tx_week in txs:
        items = conn.execute(
            "SELECT player_id, item_type FROM raw_transaction_items WHERE transaction_id=?", (tx_id,)
        ).fetchall()
        added = next((pid for pid, it in items if it == "ADD"), None)
        dropped = next((pid for pid, it in items if it == "DROP"), None)
        if added is None:
            continue

        horizon_end = tx_week + horizon
        is_complete = latest_week >= horizon_end

        # points come from whatever roster held this player each week — use
        # raw_roster_entries since that's where the already-league-scored
        # points live (stats_json is the universal raw stat line, not points).
        added_pts = conn.execute(
            """
            SELECT SUM(points_scored) FROM raw_roster_entries
            WHERE league_id=? AND season_year=? AND player_id=? AND week > ? AND week <= ?
            """,
            (league_id, season_year, added, tx_week, min(horizon_end, latest_week)),
        ).fetchone()[0]

        dropped_pts = None
        if dropped is not None:
            dropped_pts = conn.execute(
                """
                SELECT SUM(r.points_scored) FROM raw_roster_entries r
                WHERE r.season_year=? AND r.player_id=? AND r.week > ? AND r.week <= ?
                """,
                (season_year, dropped, tx_week, min(horizon_end, latest_week)),
            ).fetchone()[0]

        net = None
        if added_pts is not None and dropped_pts is not None:
            net = added_pts - dropped_pts

        conn.execute(
            """
            INSERT INTO derived_waiver_moves
                (transaction_id, player_added, player_dropped, points_added_over_horizon,
                 points_dropped_over_horizon, net_value, horizon_weeks, is_complete, calc_version, calculated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (transaction_id) DO UPDATE SET
                points_added_over_horizon = excluded.points_added_over_horizon,
                points_dropped_over_horizon = excluded.points_dropped_over_horizon,
                net_value = excluded.net_value, is_complete = excluded.is_complete,
                calc_version = excluded.calc_version, calculated_at = excluded.calculated_at
            """,
            (tx_id, added, dropped, added_pts, dropped_pts, net, horizon, int(is_complete), CALC_VERSION, now()),
        )
        n += 1
    return n


def run() -> int:
    print("Phase 5 — Tier 0-2 analytics\n")
    conn = connect()

    for league_id in config.LEAGUES:
        ls = conn.execute(
            "SELECT roster_slot_counts_json FROM league_seasons WHERE league_id=? AND season_year=?",
            (league_id, int(config.SEASON_YEAR)),
        ).fetchone()
        if not ls:
            print(f"League {league_id}: no league_seasons row, skipping.")
            continue
        slot_counts = {int(k): v for k, v in json.loads(ls[0]).items()}

        weeks = [w for (w,) in conn.execute(
            "SELECT DISTINCT week FROM raw_roster_entries WHERE league_id=? AND season_year=? ORDER BY week",
            (league_id, int(config.SEASON_YEAR)),
        ).fetchall()]
        latest_week = max(weeks) if weeks else 0
        print(f"=== League {league_id} — weeks with data: {weeks} ===")

        team_ids = [t for (t,) in conn.execute(
            "SELECT team_id FROM teams WHERE league_id=? AND season_year=?", (league_id, int(config.SEASON_YEAR))
        ).fetchall()]

        for week in weeks:
            for team_id in team_ids:
                calc_team_week(conn, league_id, int(config.SEASON_YEAR), week, team_id, slot_counts)
            backfill_score_ranks(conn, league_id, int(config.SEASON_YEAR), week)
        conn.commit()
        print(f"  derived_team_week: {len(weeks) * len(team_ids)} rows")

        for team_id in team_ids:
            calc_team_season(conn, league_id, int(config.SEASON_YEAR), latest_week, team_id)
        conn.commit()
        print(f"  derived_team_season (through week {latest_week}): {len(team_ids)} rows")

        n_moves = calc_waiver_moves(conn, league_id, int(config.SEASON_YEAR), latest_week)
        conn.commit()
        print(f"  derived_waiver_moves: {n_moves} rows (horizon={config.WAIVER_TRADE_ROI_HORIZON_WEEKS}wk, all incomplete until week {latest_week + config.WAIVER_TRADE_ROI_HORIZON_WEEKS if latest_week else '?'})")
        print()

    conn.close()
    print("Phase 5 calculation complete.")
    return 0


if __name__ == "__main__":
    sys.exit(run())
