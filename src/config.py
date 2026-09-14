"""Central configuration.

Everything league-specific lives here so nothing is hard-coded across
modules. Two leagues are tracked from day one — the schema treats league_id
as first-class throughout (mirroring the FPL project's design, which was
already multi-league-shaped even though it only ever populated one).

Secrets (ESPN_S2, ESPN_SWID) load from .env, which is gitignored and never
committed. Nothing here is guessed: SEASON_YEAR and the credentials must be
set explicitly or Phase 1 fails loudly rather than assuming a value.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# --- Leagues ------------------------------------------------------------
# label is the owner's own team name in that league — a hint for identifying
# "you" in Phase 1, not yet confirmed against live data.

LEAGUES = {
    1618731: {"my_team_hint": "Goff Is My Copilot"},
    581297461: {"my_team_hint": "LaPorta Authority"},
}

SEASON_YEAR = os.environ.get("SEASON_YEAR")  # e.g. "2025" — set in .env

# --- Credentials ----------------------------------------------------------
# Required for a private league. None if unset — callers must fail loudly
# rather than request unauthenticated and misread a 401 as "league empty."

ESPN_S2 = os.environ.get("ESPN_S2") or None
ESPN_SWID = os.environ.get("ESPN_SWID") or None

# --- HTTP -------------------------------------------------------------------

BASE_URL = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons"
# fantasy.espn.com itself only serves the website (redirects/HTML) — found
# live during Phase 1 (2026-09-13): a plain request to it 302-redirected
# instead of returning JSON, while this lm-api-reads subdomain correctly
# 401'd with no cookies (a real auth gate, not a missing/wrong endpoint).

USER_AGENT = (
    "espn-ffl-league-intelligence/0.1 (private league analytics; "
    "single daily request cycle)"
)

REQUEST_DELAY_SECONDS = 1.0
REQUEST_TIMEOUT_SECONDS = 20
MAX_RETRIES = 3
BACKOFF_BASE_SECONDS = 2.0  # 2s, 4s, 8s

# --- Analytics gates --------------------------------------------------------
# Sized down from FPL's GW10/GW15 thresholds to fit a ~14-17 week NFL season.
# Confirmed by the owner 2026-09-13 (SPEC.md §13) — not a guess left unconfirmed.

GATE_LUCK_METRICS = 5
GATE_POWER_RANKINGS = 5
GATE_PLAYOFF_PROJECTIONS = 7
WAIVER_TRADE_ROI_HORIZON_WEEKS = 3

# --- Paths ------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = REPO_ROOT / "db" / "league.sqlite"
PHASE1_OUTPUT = REPO_ROOT / "phase1_output"
PHASE1_PAYLOADS = PHASE1_OUTPUT / "payloads"
REPORTS_DIR = REPO_ROOT / "reports"
DIGEST_DIR = REPO_ROOT / "digest"
