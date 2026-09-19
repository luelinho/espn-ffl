"""Opt-in, game-day live-refresh mode — NOT the scheduled daily job.

Self-pacing: each cycle first checks whether any real NFL game is actually
in progress right now (raw_pro_games.in_progress, refreshed from ESPN's
own proTeamSchedules — two cheap requests, not the full pipeline). If one
is live, runs the full pipeline (daily_sync -> calculate -> recap -> digest
-> build_dashboard) and loops again after LIVE_REFRESH_SECONDS (default
90s). If nothing is live, it does NOT re-poll scores — instead it only
checks for real waiver/free-agent/trade activity (load_transactions, no
load_week/load_standings — the scheduled daily job already covers those
once a day) and still rebuilds the local digest/dashboard so the activity
feed stays current, then loops again after the much longer
IDLE_REFRESH_SECONDS (default 900s). Owner's exact ask, 2026-09-14:
"if there's a game, update the fantasy score every 90 seconds, otherwise
we do not update on non-game days, unless it's to update rosters and
transfers."

Safe to just leave running across a whole Sunday (or a whole week) — it
paces itself up and down on its own rather than needing to be started and
stopped around kickoff.

If this repo has a `origin` remote (i.e. it's been pushed to GitHub),
each successful cycle also commits and pushes the freshly-written files —
that push is what makes the public GitHub Pages site update on the same
90s live cadence (owner's ask, 2026-09-17): GitHub Actions' `schedule`
trigger can't reliably hit 90 seconds on its own (cron's floor is one
minute, and runs are often delayed further), so this local loop pushing
on its own cadence is the only way to get real 90s precision on the
public site too. A `.github/workflows/pages-deploy.yml` redeploys Pages
automatically on every push to `main` that touches `dashboard.html`,
whether that push comes from here or from the once-daily scheduled job.

Pair with an open dashboard.html: build_dashboard.py embeds a matching
auto-reload, so the page picks up each freshly-written file on its own.

Usage:
    python -m src.live_refresh
    python -m src.live_refresh --live-interval 60 --idle-interval 600  # override, seconds
    (Ctrl+C to stop)
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from datetime import datetime, timezone

from . import calculate, config, daily_sync, digest, ingest, recap
from . import build_dashboard as build_dashboard_module
from .espn_client import ESPNClient

STEPS = [
    ("daily_sync", daily_sync.run),
    ("calculate", calculate.run),
    ("recap", recap.run),
    ("digest", digest.run),
    ("build_dashboard", build_dashboard_module.run),
]

# calculate, recap, digest, build_dashboard — everything after daily_sync,
# reused for the idle cycle's own lightweight ingestion step below.
POST_INGEST_STEPS = STEPS[1:]


def any_game_live() -> bool:
    """Cheap check (current-week lookup + proTeamSchedules — 2 requests
    total, vs. the full pipeline's ~10) for whether a real NFL game is in
    progress anywhere right now. Uses the first configured league's
    current matchup period, since the real-world NFL week is the same
    fact regardless of which league is asking."""
    if not (config.ESPN_S2 and config.ESPN_SWID and config.SEASON_YEAR):
        return False
    conn = ingest.connect()
    client = ESPNClient(archive_dir=config.PHASE1_PAYLOADS, verbose=False)
    try:
        league_id = next(iter(config.LEAGUES))
        res = client.get_league(league_id, config.SEASON_YEAR, views=["mSettings"])
        if not res.ok:
            return False
        week = res.json_body["status"]["currentMatchupPeriod"]
        ingest.load_pro_games(conn, client, config.SEASON_YEAR, week)
        row = conn.execute(
            "SELECT COUNT(*) FROM raw_pro_games WHERE season_year=? AND week=? AND in_progress=1",
            (int(config.SEASON_YEAR), week),
        ).fetchone()
        return row[0] > 0
    finally:
        conn.close()


def push_to_github() -> None:
    """Best-effort: push the freshly-written files to GitHub so the public
    Pages site picks them up via the push-triggered pages-deploy workflow —
    the actual mechanism behind the GitHub dashboard updating every 90
    seconds during a live game (owner's ask, 2026-09-17). GitHub Actions'
    own `schedule` trigger can't do that: cron's floor is one minute and
    scheduled runs are often delayed well past their nominal time under
    load, so real 90s precision can only come from this local loop pushing
    on its own live cadence — not from anything running on GitHub's side.
    Quietly does nothing if this repo has no `origin` remote yet (never
    pushed to GitHub), and never lets a push failure crash the live loop —
    a rejected push (e.g. the scheduled daily job committed in the
    meantime) just means this cycle's update waits for the next one.

    Real bug found live, 2026-09-19: an earlier version of this function
    ran `git pull --rebase` without ever checking whether it actually
    succeeded. When it hit a genuine conflict, the repo was left stuck
    mid-rebase — every cycle after that kept committing on top of the
    broken state for hours, silently failing to push each time, until a
    human noticed the public site had gone stale. Two fixes: prefer this
    cycle's freshly-generated content on any conflict (`-X theirs`) —
    these are machine-generated data snapshots, so "newest wins" is the
    correct policy, not something to leave half-resolved — and if the
    rebase still fails despite that, abort it immediately so the repo is
    never left mid-rebase across cycles."""
    try:
        remote = subprocess.run(["git", "remote", "get-url", "origin"], cwd=config.REPO_ROOT,
                                 capture_output=True, text=True, timeout=10)
        if remote.returncode != 0:
            return
        subprocess.run(["git", "add", "db/league.sqlite", "digest/season.json", "dashboard.html"],
                        cwd=config.REPO_ROOT, check=True, timeout=10)
        staged = subprocess.run(["git", "diff", "--staged", "--quiet"], cwd=config.REPO_ROOT, timeout=10)
        if staged.returncode == 0:
            return  # nothing actually changed this cycle
        subprocess.run(["git", "commit", "-m", f"Live sync {datetime.now(timezone.utc).isoformat()}"],
                        cwd=config.REPO_ROOT, check=True, timeout=10)

        rebase = subprocess.run(["git", "pull", "--rebase", "-X", "theirs", "origin", "main"],
                                 cwd=config.REPO_ROOT, capture_output=True, text=True, timeout=30)
        if rebase.returncode != 0:
            subprocess.run(["git", "rebase", "--abort"], cwd=config.REPO_ROOT, timeout=10)
            print(f"  GitHub rebase failed, aborted cleanly (will retry next cycle): {rebase.stderr.strip()[:200]}")
            return

        push = subprocess.run(["git", "push", "origin", "main"], cwd=config.REPO_ROOT,
                               capture_output=True, text=True, timeout=20)
        if push.returncode == 0:
            print("  Pushed to GitHub — Pages will redeploy automatically.")
        else:
            print(f"  GitHub push failed (will retry next cycle): {push.stderr.strip()[:200]}")
    except Exception as exc:  # noqa: BLE001 — a live loop must not die over a push failure
        print(f"  GitHub push skipped: {exc!r}")


def run_steps(steps) -> bool:
    ok = True
    for name, step_fn in steps:
        try:
            code = step_fn()
        except Exception as exc:  # noqa: BLE001 — a live loop must not die on one bad cycle
            print(f"  [{name}] raised {exc!r} — skipping rest of this cycle")
            ok = False
            break
        if code:
            print(f"  [{name}] exited {code} — skipping rest of this cycle")
            ok = False
            break
    return ok


def run_live_cycle() -> bool:
    ok = run_steps(STEPS)
    if ok:
        push_to_github()
    return ok


def run_idle_cycle() -> bool:
    """Non-game-day cycle — catches real waiver/free-agent/trade activity
    without re-polling scores that can't be changing. Skips
    load_week/load_standings (the scheduled daily job already covers
    those once a day); still reruns calculate/recap/digest/build_dashboard
    afterward, since those are free and local, so the activity feed and
    any roster change show up right away rather than waiting for the next
    live window."""
    if not (config.ESPN_S2 and config.ESPN_SWID and config.SEASON_YEAR):
        print("  FAILED: .env is missing ESPN_S2 / ESPN_SWID / SEASON_YEAR.")
        return False
    conn = ingest.connect()
    client = ESPNClient(archive_dir=config.PHASE1_PAYLOADS, verbose=True)
    try:
        for league_id in config.LEAGUES:
            n_tx = ingest.load_transactions(conn, client, league_id, config.SEASON_YEAR)
            print(f"  League {league_id}: {n_tx} transactions (roster/waiver/trade check only)")
    finally:
        conn.close()
    ok = run_steps(POST_INGEST_STEPS)
    if ok:
        push_to_github()
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-interval", type=int, default=config.LIVE_REFRESH_SECONDS,
                         help=f"seconds between refreshes while a game is live (default {config.LIVE_REFRESH_SECONDS})")
    parser.add_argument("--idle-interval", type=int, default=config.IDLE_REFRESH_SECONDS,
                         help=f"seconds between roster/transaction-only checks when nothing is live (default {config.IDLE_REFRESH_SECONDS})")
    args = parser.parse_args()

    print(f"Live refresh mode — {args.live_interval}s while a game is live, "
          f"{args.idle_interval}s (rosters/transactions only) otherwise. Ctrl+C to stop.")
    print("This does not change the scheduled daily job — it's a separate, opt-in loop.\n")

    try:
        while True:
            started = datetime.now(timezone.utc)
            live = any_game_live()
            print(f"[{started.strftime('%H:%M:%S')} UTC] {'LIVE — a game is in progress' if live else 'idle — no game in progress'}, refreshing...")
            ok = run_live_cycle() if live else run_idle_cycle()
            interval = args.live_interval if live else args.idle_interval
            elapsed = (datetime.now(timezone.utc) - started).total_seconds()
            print(f"  {'done' if ok else 'done with errors'} in {elapsed:.1f}s — next check in {max(1, interval - elapsed):.0f}s\n")
            time.sleep(max(1, interval - elapsed))
    except KeyboardInterrupt:
        print("\nLive refresh stopped.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
