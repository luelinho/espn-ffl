"""Opt-in, game-day live-refresh mode — NOT the scheduled daily job.

Loops the full pipeline (daily_sync -> calculate -> recap -> digest ->
build_dashboard) every LIVE_REFRESH_SECONDS (default 4 minutes). Start it
manually while actively watching games; the scheduled GitHub Actions job
still runs once daily as before, unaffected — this is a separate,
session-scoped mode you start and stop yourself, not a change to that
cadence.

Pair with an open dashboard.html: build_dashboard.py embeds a matching
auto-reload, so the page picks up each freshly-written file on its own.

Usage:
    python -m src.live_refresh
    python -m src.live_refresh --interval 180   # override, seconds
    (Ctrl+C to stop)
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone

from . import calculate, config, daily_sync, digest, recap
from . import build_dashboard as build_dashboard_module

STEPS = [
    ("daily_sync", daily_sync.run),
    ("calculate", calculate.run),
    ("recap", recap.run),
    ("digest", digest.run),
    ("build_dashboard", build_dashboard_module.run),
]


def run_once() -> bool:
    ok = True
    for name, step_fn in STEPS:
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--interval", type=int, default=config.LIVE_REFRESH_SECONDS,
                         help=f"seconds between refreshes (default {config.LIVE_REFRESH_SECONDS})")
    args = parser.parse_args()

    print(f"Live refresh mode — every {args.interval}s. Ctrl+C to stop.")
    print("This does not change the scheduled daily job — it's a separate, opt-in loop.\n")

    try:
        while True:
            started = datetime.now(timezone.utc)
            print(f"[{started.strftime('%H:%M:%S')} UTC] refreshing...")
            ok = run_once()
            elapsed = (datetime.now(timezone.utc) - started).total_seconds()
            print(f"  {'done' if ok else 'done with errors'} in {elapsed:.1f}s\n")
            time.sleep(max(1, args.interval - elapsed))
    except KeyboardInterrupt:
        print("\nLive refresh stopped.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
