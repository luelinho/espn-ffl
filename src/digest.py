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
import mimetypes
import sys
from datetime import datetime, timezone

import requests

from . import config
from .ingest import connect

LOGO_CACHE_DIR = config.REPO_ROOT / "digest" / ".logo_cache"


def fetch_logo_b64(url: str, league_id: int, team_id: int) -> str | None:
    """Fetch and cache a team's logo, embedded as a correctly-typed data URI.

    Two real bugs found by inspecting the cache directly: (1) ESPN team logos
    are a mix of PNG, JPEG, and SVG sources, but every one was being wrapped
    as `data:image/png` regardless of actual type — a raster PNG decoder
    can't parse raw SVG XML, so any SVG-sourced team logo rendered as a
    broken/missing image in the browser. Fixed by deriving the real MIME
    type from the URL's extension. (2) The cache filename was keyed only by
    team_id, but ESPN team IDs are assigned per-league starting at 1, so two
    leagues' same-numbered teams silently shared (and could steal) each
    other's cached logo bytes. Fixed by keying the cache on league_id too.
    """
    if not url:
        return None
    LOGO_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = LOGO_CACHE_DIR / f"team_{league_id}_{team_id}.img"
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
    mime = mimetypes.guess_type(url)[0] or "image/png"
    return f"data:{mime};base64," + base64.b64encode(cache_path.read_bytes()).decode()


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


def teams_with_live_player(conn, league_id: int, season_year: int, week: int, game_status: dict[int, str]) -> set[int]:
    """Fantasy team_ids with at least one starter whose real NFL game is
    currently in progress — the actual meaning of "LIVE" a viewer expects
    (their score could still move right now), not just "this fantasy week
    hasn't been finalized by ESPN yet." Real bug found live, 2026-09-15:
    the LIVE badge was driven purely by raw_matchups.status != 'final',
    so it stayed lit for an entire week even when every real NFL game
    that week was already Final and nothing could possibly still change —
    confirmed by screenshot, not a display nit."""
    rows = conn.execute(
        """
        SELECT DISTINCT r.team_id, p.pro_team_id
        FROM raw_roster_entries r JOIN players p ON p.player_id = r.player_id
        WHERE r.league_id=? AND r.season_year=? AND r.week=? AND r.is_starter=1
        """,
        (league_id, season_year, week),
    ).fetchall()
    return {team_id for team_id, pro_team_id in rows if game_status.get(pro_team_id) == "live"}


def week_matchups(conn, league_id: int, season_year: int, week: int, live_teams: set[int] = frozenset()) -> list[dict]:
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
        {"a": {"team_id": a, "name": an, "score": sa}, "b": {"team_id": b, "name": bn, "score": sb},
         "live": status != "final" and (a in live_teams or b in live_teams)}
        for a, an, sa, b, bn, sb, status in rows
    ]


def game_status_map(conn, season_year: int, week: int) -> dict[int, str]:
    """pro_team_id -> 'not_started' | 'live' | 'final'. A team missing from
    this map has a bye that week (no game at all) — confirmed real from
    ESPN's proTeamSchedules (2026-09-14): `percentComplete` reaches 100
    once a game ends, `inProgress` is true while it's live. Real bug found
    testing this: `detail == 'Final'` looks right but misses overtime games
    (`detail` is literally 'Final/OT' there) — a Lions/Bills OT game showed
    as 'not_started' with real settled stats already in, a real
    misclassification, not a display nit. percent_complete >= 100 is the
    correct, robust signal; `detail` stays stored for display only."""
    rows = conn.execute(
        "SELECT home_team_id, away_team_id, in_progress, percent_complete FROM raw_pro_games WHERE season_year=? AND week=?",
        (season_year, week),
    ).fetchall()
    status: dict[int, str] = {}
    for home_id, away_id, in_progress, percent_complete in rows:
        if (percent_complete or 0) >= 100:
            s = "final"
        elif in_progress:
            s = "live"
        else:
            s = "not_started"
        status[home_id] = s
        status[away_id] = s
    return status


def game_info_map(conn, season_year: int, week: int) -> dict[int, dict]:
    """pro_team_id -> {opp_abbrev, own_score, opp_score, is_home, detail,
    kickoff_utc} — the same raw_pro_games rows game_status_map() reads, plus
    the score/opponent/clock detail needed to show a real per-player game
    line (e.g. "@LAR 27-7 Final"), joined against pro_teams for abbrevs."""
    rows = conn.execute(
        """
        SELECT g.home_team_id, g.away_team_id, g.home_score, g.away_score, g.detail, g.kickoff_utc,
               ht.abbrev, at.abbrev
        FROM raw_pro_games g
        JOIN pro_teams ht ON ht.pro_team_id = g.home_team_id AND ht.season_year = g.season_year
        JOIN pro_teams at ON at.pro_team_id = g.away_team_id AND at.season_year = g.season_year
        WHERE g.season_year=? AND g.week=?
        """,
        (season_year, week),
    ).fetchall()
    info: dict[int, dict] = {}
    for home_id, away_id, home_score, away_score, detail, kickoff, home_abbr, away_abbr in rows:
        info[home_id] = {"opp_abbrev": away_abbr, "own_score": home_score, "opp_score": away_score,
                          "is_home": True, "detail": detail, "kickoff_utc": kickoff}
        info[away_id] = {"opp_abbrev": home_abbr, "own_score": away_score, "opp_score": home_score,
                          "is_home": False, "detail": detail, "kickoff_utc": kickoff}
    return info


def injury_map(conn) -> dict[int, dict]:
    """player_id -> {injury_status, ownership_pct} from each player's most
    recent raw_player_snapshots row. That table existed in schema since
    Phase 2 but nothing ever wrote to it — mRoster's player object already
    carries injuryStatus/ownership.percentOwned, just wasn't being
    persisted; ingest.load_week() now captures one row per player per day."""
    rows = conn.execute(
        """
        SELECT s.player_id, s.injury_status, s.ownership_pct
        FROM raw_player_snapshots s
        JOIN (SELECT player_id, MAX(snapshot_date) AS md FROM raw_player_snapshots GROUP BY player_id) latest
          ON latest.player_id = s.player_id AND latest.md = s.snapshot_date
        """
    ).fetchall()
    return {pid: {"injury_status": status, "ownership_pct": pct} for pid, status, pct in rows}


def _td_label(td: float | None) -> str | None:
    if not td:
        return None
    return "TD" if td == 1 else f"{td:.0f} TD"


def _stat_line(position_id: int | None, stats_json: str | None) -> str | None:
    """Compact per-player stat line, ESPN-app style — one headline category
    per position (passing for QB, rushing for RB, receiving for WR/TE,
    made/attempted for K, turnovers + points-allowed for D/ST), matching
    what ESPN's own matchup card shows (it doesn't show a RB's incidental
    receiving line either — confirmed against the real card, 2026-09-14).

    Stat IDs are confirmed empirically against real week-1 box scores, not
    assumed from any published mapping (there is no ESPN-documented key for
    these — CLAUDE.md rule 7 says don't guess at the API). E.g. ids 3/4/20
    cross-checked against Jared Goff's real 206 YDS/2 TD and Brock Purdy's
    205 YDS/3 TD/1 INT; ids 24/25 against D'Andre Swift's exact 124 YDS/3
    TD; ids 53/42/43 against A.J. Brown's exact 3 REC/26 YDS and CeeDee
    Lamb/Ladd McConkey's receiving TDs; ids 83/84/86/87 against Cam
    Little's exact 2/2 FG, 4/4 XP.

    D/ST's points-allowed field is id 120, NOT id 100 — id 100 was
    originally (wrongly) confirmed against the Jaguars D/ST's real
    INT/FR/10 PA line, but that was a coincidence: id 100 is actually
    `defensiveSacks * 2` (id 99 is sacks; 100/99 == 2.0 in every real
    example checked, 10 of 10 across week 1-2 box scores), and the
    Jaguars just happened to have 5 sacks that week (5*2 == 10 == their
    real points allowed). Re-confirmed 2026-09-18 against 10 real D/ST
    box scores: id 120 matched real points allowed in all 10; id 100
    matched only that one coincidental case. See id 91/92/etc's
    points-allowed-bracket flags (0.0/1.0) for an independent
    cross-check of which bracket a real value should fall in.
    """
    if not stats_json:
        return None
    s = json.loads(stats_json)

    if position_id == 1:  # QB
        yds, td, ints = s.get("3"), s.get("4"), s.get("20")
        if yds is None:
            return None
        parts = [f"{yds:.0f} YDS", _td_label(td)]
        if ints:
            parts.append("INT" if ints == 1 else f"{ints:.0f} INT")
        return ", ".join(p for p in parts if p)
    if position_id == 2:  # RB
        yds, td = s.get("24"), s.get("25")
        if yds is None:
            return None
        return ", ".join(p for p in [f"{yds:.0f} YDS", _td_label(td)] if p)
    if position_id in (3, 4):  # WR / TE
        rec, yds, td = s.get("53"), s.get("42"), s.get("43")
        if rec is None:
            return None
        return ", ".join(p for p in [f"{rec:.0f} REC", f"{(yds or 0):.0f} YDS", _td_label(td)] if p)
    if position_id == 5:  # K
        fgm, fga, xpm, xpa = s.get("83"), s.get("84"), s.get("86"), s.get("87")
        parts = []
        if fga:
            parts.append(f"{fgm or 0:.0f}/{fga:.0f} FG")
        if xpa:
            parts.append(f"{xpm or 0:.0f}/{xpa:.0f} XP")
        return ", ".join(parts) if parts else None
    if position_id == 16:  # D/ST
        ints, fr, pa = s.get("95"), s.get("96"), s.get("120")
        parts = []
        if ints:
            parts.append("INT" if ints == 1 else f"{ints:.0f} INT")
        if fr:
            parts.append("FR" if fr == 1 else f"{fr:.0f} FR")
        if pa is not None:
            parts.append(f"{pa:.0f} PA")
        return ", ".join(parts) if parts else None
    return None


def roster_for(conn, league_id: int, season_year: int, team_id: int, week: int, game_status: dict[int, str],
                game_info: dict[int, dict], injuries: dict[int, dict]) -> list[dict]:
    rows = conn.execute(
        """
        SELECT p.full_name, p.default_position_id, r.is_starter, r.lineup_slot_id, r.points_scored,
               p.pro_team_id, p.player_id, s.stats_json
        FROM raw_roster_entries r
        JOIN players p ON p.player_id = r.player_id
        LEFT JOIN raw_player_week_stats s
          ON s.player_id = r.player_id AND s.season_year = r.season_year AND s.week = r.week
        WHERE r.league_id=? AND r.season_year=? AND r.team_id=? AND r.week=?
        ORDER BY r.is_starter DESC, r.points_scored DESC
        """,
        (league_id, season_year, team_id, week),
    ).fetchall()
    out = []
    for n, pos, st, slot, pts, pt, pid, stats_json in rows:
        gi = game_info.get(pt, {})
        inj = injuries.get(pid, {})
        inj_status = inj.get("injury_status")
        out.append({
            "name": n, "position_id": pos, "is_starter": bool(st), "slot_id": slot, "points": pts,
            "pro_team_id": pt, "game_status": game_status.get(pt, "bye"),
            "opponent": gi.get("opp_abbrev"), "own_score": gi.get("own_score"), "opp_score": gi.get("opp_score"),
            "is_home": gi.get("is_home"), "game_detail": gi.get("detail"), "kickoff_utc": gi.get("kickoff_utc"),
            "stat_line": _stat_line(pos, stats_json),
            "injury_status": inj_status if inj_status not in (None, "ACTIVE") else None,
        })
    return out


def team_detail(conn, league_id: int, season_year: int, team_id: int, week: int, game_status: dict[int, str],
                 game_info: dict[int, dict], injuries: dict[int, dict]) -> dict:
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
        "roster": roster_for(conn, league_id, season_year, team_id, week, game_status, game_info, injuries),
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


def recent_scoring_events(conn, league_id: int, season_year: int, limit: int = 20) -> list[dict]:
    """Real point increases detected between two syncs of a still-live
    week — for the Home ticker ("X just scored, owned by Y"), owner's ask
    2026-09-15. See ingest.load_week()'s scoring_events insert for exactly
    when these fire: never on a backfill/rebuild replaying already-final
    history, only while a week was genuinely live between two real syncs."""
    rows = conn.execute(
        """
        SELECT e.detected_at, e.week, e.team_id, e.points_before, e.points_after, e.is_starter,
               p.full_name, t.team_name, m.display_name
        FROM scoring_events e
        JOIN players p ON p.player_id = e.player_id
        JOIN teams t ON t.league_id=e.league_id AND t.season_year=e.season_year AND t.team_id=e.team_id
        LEFT JOIN managers m ON m.manager_id = t.manager_id
        WHERE e.league_id=? AND e.season_year=?
        ORDER BY e.detected_at DESC
        LIMIT ?
        """,
        (league_id, season_year, limit),
    ).fetchall()
    return [
        {"detected_at": da, "week": wk, "team_id": tid, "points_before": pb, "points_after": pa,
         "delta": round(pa - pb, 2), "is_starter": bool(st), "player": pname, "team_name": tn, "manager": mgr}
        for da, wk, tid, pb, pa, st, pname, tn, mgr in rows
    ]


def league_activity(conn, league_id: int, season_year: int, limit: int = 12) -> list[dict]:
    """Recent real roster moves — waiver claims, free-agent adds/drops, and
    completed trades — for the whole league, not just the owner's own team
    (waiver_moves() above is owner-scoped; this is the Home page's "what
    did I miss" feed). Excludes DRAFT items (pre-season) and LINEUP items
    (starter/bench moves, not a real transaction) since neither is
    activity worth seeing in a feed. EXECUTED only — a PENDING or CANCELED
    trade proposal never happened. Grouped by transaction_id: ESPN records
    a single waiver swap's add+drop as either one transaction or two
    (confirmed live, 2026-09-14, both shapes exist in real data) — either
    way each transaction_id becomes one feed entry, so a paired swap shows
    as one line when ESPN grouped it and two when it didn't, never merged
    or split ourselves.
    """
    rows = conn.execute(
        """
        SELECT t.transaction_id, t.type, t.proposed_at, t.team_id,
               i.item_type, p.full_name, i.from_team_id, i.to_team_id
        FROM raw_transaction_items i
        JOIN raw_transactions t ON t.transaction_id = i.transaction_id
        JOIN players p ON p.player_id = i.player_id
        WHERE t.league_id=? AND t.season_year=? AND t.status='EXECUTED'
          AND i.item_type IN ('ADD','DROP','TRADE')
        ORDER BY t.proposed_at DESC
        """,
        (league_id, season_year),
    ).fetchall()

    team_info = {t["team_id"]: (t["team_name"], t["manager"]) for t in team_list(conn, league_id, season_year)}

    groups: dict[str, dict] = {}
    order: list[str] = []
    for txid, ttype, proposed_at, txteam, item_type, pname, from_id, to_id in rows:
        if txid not in groups:
            groups[txid] = {"type": ttype, "proposed_at": proposed_at, "team_id": txteam,
                             "adds": [], "drops": [], "trade_items": []}
            order.append(txid)
        g = groups[txid]
        if item_type == "ADD":
            g["adds"].append(pname)
        elif item_type == "DROP":
            g["drops"].append(pname)
        else:
            g["trade_items"].append({"player": pname, "from_team_id": from_id, "to_team_id": to_id})

    activity = []
    for txid in order[:limit]:
        g = groups[txid]
        if g["trade_items"]:
            team_ids = sorted({x["from_team_id"] for x in g["trade_items"]} | {x["to_team_id"] for x in g["trade_items"]})
            sides = [
                {"team_id": tid, "team_name": team_info.get(tid, (f"Team {tid}", None))[0],
                 "manager": team_info.get(tid, (None, None))[1],
                 "received": [x["player"] for x in g["trade_items"] if x["to_team_id"] == tid]}
                for tid in team_ids
            ]
            activity.append({"kind": "trade", "proposed_at": g["proposed_at"], "sides": sides})
        else:
            team_name, manager = team_info.get(g["team_id"], (None, None))
            activity.append({
                "kind": "waiver" if g["type"] == "WAIVER" else "freeagent",
                "proposed_at": g["proposed_at"], "team_id": g["team_id"],
                "team_name": team_name, "manager": manager,
                "adds": g["adds"], "drops": g["drops"],
            })
    return activity


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
    gstatus = game_status_map(conn, season_year, week)
    ginfo = game_info_map(conn, season_year, week)
    inj = injury_map(conn)
    live_teams = teams_with_live_player(conn, league_id, season_year, week, gstatus)

    return {
        **info,
        "current_week": week,
        "teams": teams,
        "standings": standings(conn, league_id, season_year, week),
        "this_week": {"week": week, "matchups": week_matchups(conn, league_id, season_year, week, live_teams)},
        "leaderboard": leaderboard(conn, league_id, season_year, week),
        "my_team_detail": team_detail(conn, league_id, season_year, info["my_team_id"], week, gstatus, ginfo, inj) if info["my_team_id"] else None,
        "teams_detail": {str(t["team_id"]): team_detail(conn, league_id, season_year, t["team_id"], week, gstatus, ginfo, inj) for t in teams},
        "waiver_moves": waiver_moves(conn, league_id, season_year, info["my_team_id"]) if info["my_team_id"] else [],
        "activity": league_activity(conn, league_id, season_year),
        "scoring_events": recent_scoring_events(conn, league_id, season_year),
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
                b64 = fetch_logo_b64(t.get("logo"), league_id, t["id"])
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
