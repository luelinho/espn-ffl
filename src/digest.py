"""Phase 7 — digest export for the dashboard.

Builds digest/season.json: a compact, current-state snapshot covering BOTH
leagues, so the dashboard itself never touches SQL. Every number traces to
a raw or derived table.

Team logos are embedded as base64 at build time (not referenced by URL) —
verified live that ESPN's logo CDN (mystique-api.fantasy.espn.com) requires
the same auth cookies as the main API, scoped to that specific domain, so a
plain browser opening the finished dashboard.html could never load them
directly. Same embed-at-build-time pattern the FPL project used for club
badges.

Usage:
    python -m src.digest
"""

from __future__ import annotations

import base64
import json
import sys
from datetime import datetime, timezone

import requests

from . import config
from .ingest import connect

LOGO_CACHE_DIR = config.REPO_ROOT / "digest" / ".logo_cache"


def fetch_logo_b64(url: str, team_id: int) -> str | None:
    if not url:
        return None
    LOGO_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = LOGO_CACHE_DIR / f"team_{team_id}.img"
    if not cache_path.exists():
        try:
            s = requests.Session()
            domain = url.split("/")[2]
            s.cookies.set("espn_s2", config.ESPN_S2, domain=domain)
            s.cookies.set("SWID", config.ESPN_SWID, domain=domain)
            resp = s.get(url, timeout=10)
            resp.raise_for_status()
            cache_path.write_bytes(resp.content)
        except requests.RequestException:
            return None
    return "data:image/png;base64," + base64.b64encode(cache_path.read_bytes()).decode()


def league_info(conn, league_id: int, season_year: int) -> dict:
    row = conn.execute(
        """
        SELECT l.name, ls.team_count, ls.playoff_team_count, ls.playoff_seeding_rule,
               ls.regular_season_weeks, ls.final_week, l.my_team_hint
        FROM leagues l JOIN league_seasons ls ON ls.league_id = l.league_id AND ls.season_year = ?
        WHERE l.league_id = ?
        """,
        (season_year, league_id),
    ).fetchone()
    name, team_count, playoff_teams, seeding, reg_weeks, final_week, my_team_hint = row
    my_team = conn.execute(
        "SELECT t.team_id, t.team_name FROM teams t JOIN managers m ON m.manager_id = t.manager_id "
        "WHERE t.league_id=? AND t.season_year=? AND m.is_owner=1",
        (league_id, season_year),
    ).fetchone()
    return {
        "league_id": league_id, "name": name, "team_count": team_count,
        "playoff_team_count": playoff_teams, "playoff_seeding_rule": seeding,
        "regular_season_weeks": reg_weeks, "final_week": final_week,
        "my_team_id": my_team[0] if my_team else None,
        "my_team_name": my_team[1] if my_team else my_team_hint,
    }


def current_week(conn, league_id: int, season_year: int) -> int:
    row = conn.execute(
        "SELECT MAX(week) FROM raw_roster_entries WHERE league_id=? AND season_year=?",
        (league_id, season_year),
    ).fetchone()
    return row[0] or 1


def team_list(conn, league_id: int, season_year: int) -> list[dict]:
    rows = conn.execute(
        """
        SELECT t.team_id, t.team_name, m.display_name, m.is_owner
        FROM teams t LEFT JOIN managers m ON m.manager_id = t.manager_id
        WHERE t.league_id=? AND t.season_year=? ORDER BY t.team_name
        """,
        (league_id, season_year),
    ).fetchall()
    return [{"team_id": tid, "team_name": name, "manager": mgr, "is_owner": bool(owner)} for tid, name, mgr, owner in rows]


def standings(conn, league_id: int, season_year: int, week: int) -> list[dict]:
    rows = conn.execute(
        """
        SELECT t.team_id, t.team_name, m.display_name, s.wins, s.losses, s.ties, s.points_for, s.points_against, m.is_owner
        FROM standings_snapshots s
        JOIN teams t ON t.league_id=s.league_id AND t.season_year=s.season_year AND t.team_id=s.team_id
        LEFT JOIN managers m ON m.manager_id = t.manager_id
        WHERE s.league_id=? AND s.season_year=? AND s.week=?
        ORDER BY s.wins DESC, s.points_for DESC
        """,
        (league_id, season_year, week),
    ).fetchall()
    return [
        {"team_id": tid, "team_name": tn, "manager": mgr, "wins": w, "losses": l, "ties": t,
         "points_for": pf, "points_against": pa, "is_owner": bool(owner)}
        for tid, tn, mgr, w, l, t, pf, pa, owner in rows
    ]


def week_matchups(conn, league_id: int, season_year: int, week: int) -> list[dict]:
    rows = conn.execute(
        """
        SELECT m.team_a, ta.team_name, m.score_a, m.team_b, tb.team_name, m.score_b, m.status
        FROM raw_matchups m
        JOIN teams ta ON ta.league_id=m.league_id AND ta.season_year=m.season_year AND ta.team_id=m.team_a
        JOIN teams tb ON tb.league_id=m.league_id AND tb.season_year=m.season_year AND tb.team_id=m.team_b
        WHERE m.league_id=? AND m.season_year=? AND m.week=?
        """,
        (league_id, season_year, week),
    ).fetchall()
    return [
        {"a": {"team_id": a, "name": an, "score": sa}, "b": {"team_id": b, "name": bn, "score": sb}, "live": status != "final"}
        for a, an, sa, b, bn, sb, status in rows
    ]


def roster_for(conn, league_id: int, season_year: int, team_id: int, week: int) -> list[dict]:
    rows = conn.execute(
        """
        SELECT p.full_name, p.default_position_id, r.is_starter, r.lineup_slot_id, r.points_scored, p.pro_team_id
        FROM raw_roster_entries r JOIN players p ON p.player_id = r.player_id
        WHERE r.league_id=? AND r.season_year=? AND r.team_id=? AND r.week=?
        ORDER BY r.is_starter DESC, r.points_scored DESC
        """,
        (league_id, season_year, team_id, week),
    ).fetchall()
    return [
        {"name": n, "position_id": pos, "is_starter": bool(st), "slot_id": slot, "points": pts, "pro_team_id": pt}
        for n, pos, st, slot, pts, pt in rows
    ]


def team_detail(conn, league_id: int, season_year: int, team_id: int, week: int) -> dict:
    dw = conn.execute(
        "SELECT actual_starter_points, optimal_lineup_points, lineup_efficiency, bench_points, score_rank FROM derived_team_week "
        "WHERE league_id=? AND season_year=? AND week=? AND team_id=?",
        (league_id, season_year, week, team_id),
    ).fetchone()
    ds = conn.execute(
        "SELECT weeks_played, points_for, points_against, actual_w, actual_l, actual_t, season_lineup_efficiency, "
        "total_bench_points, is_provisional FROM derived_team_season "
        "WHERE league_id=? AND season_year=? AND team_id=? AND through_week=?",
        (league_id, season_year, team_id, week),
    ).fetchone()
    return {
        "week_stats": None if not dw else {
            "actual_points": dw[0], "optimal_points": dw[1], "efficiency": dw[2], "bench_points": dw[3], "rank": dw[4],
        },
        "season_stats": None if not ds else {
            "weeks_played": ds[0], "points_for": ds[1], "points_against": ds[2],
            "record": {"w": ds[3], "l": ds[4], "t": ds[5]},
            "lineup_efficiency": ds[6], "total_bench_points": ds[7], "is_provisional": bool(ds[8]),
        },
        "roster": roster_for(conn, league_id, season_year, team_id, week),
    }


def leaderboard(conn, league_id: int, season_year: int, week: int) -> list[dict]:
    rows = conn.execute(
        """
        SELECT t.team_id, t.team_name, m.display_name, ds.season_lineup_efficiency, ds.total_bench_points, ds.is_provisional
        FROM derived_team_season ds
        JOIN teams t ON t.league_id=ds.league_id AND t.season_year=ds.season_year AND t.team_id=ds.team_id
        LEFT JOIN managers m ON m.manager_id = t.manager_id
        WHERE ds.league_id=? AND ds.season_year=? AND ds.through_week=?
        ORDER BY ds.season_lineup_efficiency DESC
        """,
        (league_id, season_year, week),
    ).fetchall()
    return [
        {"team_id": tid, "team_name": tn, "manager": mgr, "lineup_efficiency": eff, "bench_points": bp, "is_provisional": bool(prov)}
        for tid, tn, mgr, eff, bp, prov in rows
    ]


def waiver_moves(conn, league_id: int, season_year: int, team_id: int) -> list[dict]:
    rows = conn.execute(
        """
        SELECT pa.full_name, pd.full_name, dw.points_added_over_horizon, dw.points_dropped_over_horizon,
               dw.net_value, dw.horizon_weeks, dw.is_complete, t.week
        FROM derived_waiver_moves dw
        JOIN raw_transactions t ON t.transaction_id = dw.transaction_id
        JOIN players pa ON pa.player_id = dw.player_added
        LEFT JOIN players pd ON pd.player_id = dw.player_dropped
        WHERE t.league_id=? AND t.season_year=? AND t.team_id=?
        ORDER BY t.week DESC
        """,
        (league_id, season_year, team_id),
    ).fetchall()
    return [
        {"added": a, "dropped": d, "added_pts": ap, "dropped_pts": dp, "net": net,
         "horizon_weeks": h, "is_complete": bool(c), "week": wk}
        for a, d, ap, dp, net, h, c, wk in rows
    ]


def alerts(conn, league_id: int) -> dict:
    total = conn.execute("SELECT COUNT(*) FROM data_issues WHERE resolved=0 AND league_id=?", (league_id,)).fetchone()[0]
    rows = conn.execute(
        "SELECT severity, category, description FROM data_issues WHERE resolved=0 AND league_id=? "
        "ORDER BY severity='error' DESC, severity='warning' DESC, detected_at DESC LIMIT 5",
        (league_id,),
    ).fetchall()
    return {"items": [{"severity": s, "category": c, "description": d} for s, c, d in rows], "total_unresolved": total}


def build_league_digest(conn, league_id: int, season_year: int) -> dict:
    week = current_week(conn, league_id, season_year)
    info = league_info(conn, league_id, season_year)
    teams = team_list(conn, league_id, season_year)

    return {
        **info,
        "current_week": week,
        "teams": teams,
        "standings": standings(conn, league_id, season_year, week),
        "this_week": {"week": week, "matchups": week_matchups(conn, league_id, season_year, week)},
        "leaderboard": leaderboard(conn, league_id, season_year, week),
        "my_team_detail": team_detail(conn, league_id, season_year, info["my_team_id"], week) if info["my_team_id"] else None,
        "teams_detail": {str(t["team_id"]): team_detail(conn, league_id, season_year, t["team_id"], week) for t in teams},
        "waiver_moves": waiver_moves(conn, league_id, season_year, info["my_team_id"]) if info["my_team_id"] else [],
        "alerts": alerts(conn, league_id),
    }


def build_digest() -> dict:
    conn = connect()
    season_year = int(config.SEASON_YEAR)

    # Team logos: fetch fresh via a live call (URL isn't persisted in schema —
    # it's presentation data, not a fact worth storing/versioning in raw_*).
    from .espn_client import ESPNClient
    client = ESPNClient(archive_dir=config.PHASE1_PAYLOADS, verbose=False)
    logos: dict[str, str] = {}
    for league_id in config.LEAGUES:
        res = client.get_league(league_id, config.SEASON_YEAR, views=["mTeam"])
        if res.ok:
            for t in res.json_body.get("teams", []):
                b64 = fetch_logo_b64(t.get("logo"), t["id"])
                if b64:
                    logos[f"{league_id}_{t['id']}"] = b64

    d = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "season_year": season_year,
        "leagues": {str(lid): build_league_digest(conn, lid, season_year) for lid in config.LEAGUES},
        "team_logos": logos,
    }
    conn.close()
    return d


def run() -> int:
    print("Phase 7 — digest export\n")
    d = build_digest()
    config.DIGEST_DIR.mkdir(parents=True, exist_ok=True)
    out_path = config.DIGEST_DIR / "season.json"
    out_path.write_text(json.dumps(d, indent=2))
    print(f"Wrote {out_path} ({out_path.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(run())
