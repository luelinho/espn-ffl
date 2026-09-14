"""Phase 7 — builds dashboard.html, a single self-contained file.

Data is baked in as a <script> tag at generation time (same reasoning as
the FPL project: a local file:// page can't fetch a sibling JSON file).

Visual redesign 2026-09-14: sidebar + gradient-KPI-card dashboard language
(owner-supplied reference image), still fresh/not a reskin of the FPL
dashboard. Every chart is driven by real digest data — no fabricated
trend deltas, no placeholder history beyond the weeks that actually exist.

Usage:
    python -m src.build_dashboard
"""

from __future__ import annotations

import json
import sys

from . import config

ICONS = {
    "home": '<path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V20a1 1 0 0 0 1 1h4v-6h4v6h4a1 1 0 0 0 1-1V9.5"/>',
    "myteam": '<circle cx="12" cy="8" r="3.6"/><path d="M4.5 20c0-4.2 3.4-6.8 7.5-6.8s7.5 2.6 7.5 6.8"/>',
    "league": '<rect x="3.5" y="3.5" width="7" height="7" rx="1.5"/><rect x="13.5" y="3.5" width="7" height="7" rx="1.5"/><rect x="3.5" y="13.5" width="7" height="7" rx="1.5"/><rect x="13.5" y="13.5" width="7" height="7" rx="1.5"/>',
    "managers": '<circle cx="8.5" cy="8" r="3.2"/><circle cx="16" cy="9" r="2.6"/><path d="M3 19.5c0-3.6 2.6-5.8 5.5-5.8s5.5 2.2 5.5 5.8"/><path d="M14.8 14.2c2.5.3 4.2 2.2 4.2 5.3"/>',
    "analytics": '<path d="M4 20V10"/><path d="M11 20V4"/><path d="M18 20v-7"/>',
    "bell": '<path d="M6 9.5a6 6 0 0 1 12 0c0 4 1.5 5.5 1.5 5.5H4.5S6 13.5 6 9.5Z"/><path d="M10 19a2 2 0 0 0 4 0"/>',
    "trend": '<path d="M4 15 9 9l4 3 7-8"/><path d="M16 4h4v4"/>',
    "bench": '<path d="M3 11h18"/><path d="M5 11V7a1 1 0 0 1 1-1h12a1 1 0 0 1 1 1v4"/><path d="M4 11v8"/><path d="M20 11v8"/>',
    "trophy": '<path d="M8 4h8v5a4 4 0 0 1-8 0V4Z"/><path d="M8 5H5a3 3 0 0 0 3 4"/><path d="M16 5h3a3 3 0 0 1-3 4"/><path d="M12 13v3"/><path d="M9 20h6"/><path d="M10 17h4v3h-4z"/>',
    "menu": '<path d="M4 6h16"/><path d="M4 12h16"/><path d="M4 18h16"/>',
    "close": '<path d="M6 6l12 12"/><path d="M18 6 6 18"/>',
}


def icon(name: str, size: int = 18) -> str:
    return f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">{ICONS[name]}</svg>'


CSS = """
:root {
  --bg: #140e29;
  --bg-deep: #0f0a1f;
  --sidebar: #180f30;
  --card: rgba(255,255,255,0.045);
  --card-2: rgba(255,255,255,0.065);
  --ink: #f4f2fb;
  --ink-soft: #a79cc9;
  --ink-faint: #6f6592;
  --border: rgba(255,255,255,0.09);
  --accent: #8b7cf6;
  --accent-ink: #100a20;
  --accent-soft: rgba(139,124,246,0.16);
  --ring-track: rgba(255,255,255,0.08);
  --amber-a: #f7c358; --amber-b: #ef9027;
  --blue-a: #8f7cf7; --blue-b: #5f49dd;
  --cyan-a: #34dfd6; --cyan-b: #10a3ad;
  --pink-a: #f158a3; --pink-b: #c62a83;
  --shadow: 0 1px 0 rgba(255,255,255,0.06) inset, 0 18px 40px rgba(0,0,0,0.45);
}
* { box-sizing: border-box; }
html, body { height: 100%; }
body {
  margin: 0; color: var(--ink); overflow: hidden;
  background:
    radial-gradient(1000px 560px at 15% -10%, rgba(139,124,246,0.18), transparent 55%),
    radial-gradient(900px 620px at 100% 0%, rgba(241,88,163,0.10), transparent 55%),
    var(--bg);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
}
.shell { display: flex; height: 100vh; }

/* --- nav drawer: hidden by default, slides in from the left over a
   backdrop (owner's call, 2026-09-14) — replaces both the old always-
   visible sidebar and its separate mobile fallback with one pattern that
   works at every width. --- */
.sidebar {
  position: fixed; top: 0; left: 0; width: 240px; height: 100vh; z-index: 200;
  background: var(--sidebar); border-right: 1px solid var(--border);
  padding: 20px 14px; display: flex; flex-direction: column; gap: 4px; overflow-y: auto;
  transform: translateX(-100%); transition: transform 0.22s ease;
  box-shadow: 20px 0 40px rgba(0,0,0,0.4);
}
.sidebar.open { transform: translateX(0); }
.sidebar .brand { font-weight: 800; font-size: 15px; letter-spacing: -0.01em; padding: 6px 10px 18px; display: flex; align-items: center; justify-content: space-between; }
.sidebar .brand-sub { display: block; color: var(--ink-faint); font-size: 10.5px; font-weight: 500; margin-top: 3px; }
.nav-close { background: none; border: none; color: var(--ink-soft); cursor: pointer; padding: 4px; display: flex; }
.nav-backdrop { position: fixed; inset: 0; background: rgba(5,3,12,0.55); backdrop-filter: blur(1px); z-index: 190; opacity: 0; pointer-events: none; transition: opacity 0.22s ease; }
.nav-backdrop.open { opacity: 1; pointer-events: auto; }
.navitem { display: flex; align-items: center; gap: 10px; padding: 10px 12px; border-radius: 11px; color: var(--ink-soft); font-size: 13px; font-weight: 700; cursor: pointer; }
.navitem svg { flex: none; opacity: 0.85; }
.navitem.active { background: linear-gradient(135deg, var(--blue-a), var(--blue-b)); color: #fff; }
.navitem.active svg { opacity: 1; }
.navitem:not(.active):hover { background: rgba(255,255,255,0.04); color: var(--ink); }

/* --- topbar --- */
.topbar { flex: none; display: flex; align-items: center; justify-content: space-between; gap: 14px; padding: 16px 24px; flex-wrap: wrap; border-bottom: 1px solid var(--border); }
.topbar-left { display: flex; align-items: center; gap: 14px; }
.hamburger-btn { width: 38px; height: 38px; border-radius: 10px; background: var(--card); border: 1px solid var(--border); display: flex; align-items: center; justify-content: center; color: var(--ink); cursor: pointer; flex: none; }
.hamburger-btn:hover { background: var(--card-2); }
.topbar-brand { font-weight: 800; font-size: 15px; letter-spacing: -0.01em; white-space: nowrap; }
.topbar-brand .brand-sub { display: block; color: var(--ink-faint); font-size: 10px; font-weight: 500; margin-top: 1px; }
.league-switch { display: flex; gap: 4px; background: var(--card); border: 1px solid var(--border); border-radius: 999px; padding: 4px; }
.league-switch button { border: none; background: transparent; color: var(--ink-soft); padding: 8px 16px; border-radius: 999px; font-size: 12.5px; font-weight: 700; cursor: pointer; }
.league-switch button.active { background: linear-gradient(135deg, var(--blue-a), var(--blue-b)); color: #fff; }
.league-switch button.active.league-pink { background: linear-gradient(135deg, var(--pink-a), var(--pink-b)); }
.league-switch button.active.league-purple { background: linear-gradient(135deg, var(--blue-a), var(--blue-b)); }
.topbar-icons { display: flex; align-items: center; gap: 10px; }
.refresh-note { font-size: 10.5px; color: var(--ink-faint); font-weight: 600; cursor: help; white-space: nowrap; }
.icon-btn { position: relative; width: 36px; height: 36px; border-radius: 50%; background: var(--card); border: 1px solid var(--border); display: flex; align-items: center; justify-content: center; color: var(--ink-soft); }
.icon-btn .dot { position: absolute; top: 6px; right: 6px; width: 8px; height: 8px; border-radius: 50%; background: var(--pink-a); border: 1.5px solid var(--sidebar); }
.profile-chip { display: flex; align-items: center; gap: 9px; background: var(--card); border: 1px solid var(--border); border-radius: 999px; padding: 5px 14px 5px 6px; }
.profile-chip .avatar { width: 26px; height: 26px; border-radius: 50%; background: linear-gradient(135deg, var(--pink-a), var(--pink-b)); display: flex; align-items: center; justify-content: center; font-size: 11px; font-weight: 800; color: #fff; }
.profile-chip .name { font-size: 12.5px; font-weight: 700; }
.profile-chip .role { font-size: 10px; color: var(--ink-faint); }

main { flex: 1; min-width: 0; height: 100vh; overflow: hidden; display: flex; flex-direction: column; }
.scroll-area { flex: 1; overflow-y: auto; display: flex; flex-direction: column; }
.content { padding: 4px 24px 60px; display: flex; flex-direction: column; gap: 16px; }
.page { display: none; flex-direction: column; gap: 16px; }
.page.active { display: flex; }

/* --- KPI row --- */
.kpi-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; }
@media (max-width: 900px) { .kpi-row { grid-template-columns: repeat(2, 1fr); } }
.kpi { border-radius: 16px; padding: 16px 18px; color: #fff; box-shadow: var(--shadow); position: relative; overflow: hidden; }
.kpi.amber { background: linear-gradient(135deg, var(--amber-a), var(--amber-b)); }
.kpi.blue { background: linear-gradient(135deg, var(--blue-a), var(--blue-b)); }
.kpi.cyan { background: linear-gradient(135deg, var(--cyan-a), var(--cyan-b)); }
.kpi.pink { background: linear-gradient(135deg, var(--pink-a), var(--pink-b)); }
.kpi .kpi-top { display: flex; align-items: flex-start; justify-content: space-between; }
.kpi .kpi-icon { width: 30px; height: 30px; border-radius: 9px; background: rgba(255,255,255,0.22); display: flex; align-items: center; justify-content: center; }
.kpi .value { font-size: 22px; font-weight: 800; margin-top: 10px; letter-spacing: -0.01em; }
.kpi .label { font-size: 10.5px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; opacity: 0.85; margin-top: 2px; }

/* --- card grid --- */
.grid { display: grid; gap: 14px; }
.grid-2 { grid-template-columns: 1fr 1fr; }
.grid-4 { grid-template-columns: repeat(4, 1fr); }
@media (max-width: 900px) { .grid-2, .grid-4 { grid-template-columns: 1fr 1fr; } }
@media (max-width: 620px) { .grid-2, .grid-4 { grid-template-columns: 1fr; } }
.card { background: var(--card); border: 1px solid var(--border); border-radius: 16px; padding: 18px 20px; box-shadow: var(--shadow); overflow-x: auto; }
/* One league pink, the other purple (owner's ask, 2026-09-14) — a
   consistent accent stripe so the two side-by-side leagues on Home are
   tellable apart without reading. */
.card.league-pink { border-left: 3px solid var(--pink-a); }
.card.league-purple { border-left: 3px solid var(--blue-a); }
.card-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.card-head h2 { margin: 0; font-size: 13.5px; display: flex; align-items: center; gap: 8px; }
.card-head .icon-chip { width: 22px; height: 22px; border-radius: 7px; background: var(--accent-soft); color: var(--accent); display: flex; align-items: center; justify-content: center; }
.card-head-title { display: flex; flex-direction: column; gap: 1px; min-width: 0; }
.card h3 { margin: 0 0 8px; font-size: 11.5px; color: var(--ink-soft); text-transform: uppercase; letter-spacing: 0.05em; }

table { width: 100%; border-collapse: collapse; font-size: 13px; }
th, td { text-align: left; padding: 8px 8px; border-bottom: 1px solid var(--border); }
th { color: var(--ink-soft); font-weight: 700; font-size: 10.5px; text-transform: uppercase; letter-spacing: 0.04em; }
/* "My team" gets a consistent, subtle accent tint everywhere it shows up
   among other teams (owner's ask, 2026-09-14) — standings already had
   this for table rows; the same tint now extends to the scoreboard and
   matchup headers via .mine on the specific team's own block, not the
   whole row, so it reads as "this one is you" rather than a full-row
   highlight competing with LIVE badges etc. */
tr.owner-row td { background: var(--accent-soft); }
tr.owner-row td:first-child { border-left: 2px solid var(--accent); padding-left: 6px; }
.muted { color: var(--ink-soft); font-size: 12px; }
.badge { display: inline-block; font-size: 9.5px; font-weight: 800; text-transform: uppercase; padding: 2px 7px; border-radius: 999px; }
.badge.live { background: rgba(241,88,163,0.16); color: var(--pink-a); }
.badge.prov { background: var(--accent-soft); color: var(--accent); }
.match-row { display: flex; align-items: center; gap: 10px; padding: 8px 0; border-bottom: 1px solid var(--border); font-size: 13px; cursor: pointer; border-radius: 8px; transition: background 0.15s ease; }
.match-row:hover { background: var(--card-2); }
.match-row:last-child { border-bottom: none; }
.match-row .side { display: flex; align-items: center; gap: 8px; flex: 1; min-width: 0; font-weight: 700; }
.match-row .side.right { flex-direction: row-reverse; text-align: right; }
.match-row .score { min-width: 90px; text-align: center; font-weight: 800; font-variant-numeric: tabular-nums; }
/* League activity feed (Home) — real waiver/free-agent/trade moves, so
   the owner doesn't have to open the ESPN app to see who moved. */
.activity-row { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 8px 0; border-bottom: 1px solid var(--border); font-size: 12.5px; }
.activity-row:last-child { border-bottom: none; }
.activity-main { display: flex; align-items: center; gap: 8px; min-width: 0; }
.activity-tag { flex: none; font-size: 9px; font-weight: 800; padding: 2px 6px; border-radius: 5px; text-transform: uppercase; letter-spacing: 0.02em; }
.activity-tag.waiver { background: rgba(52,223,214,0.16); color: var(--cyan-a); }
.activity-tag.freeagent { background: var(--accent-soft); color: var(--accent); }
.activity-tag.trade { background: rgba(247,195,88,0.18); color: var(--amber-a); }
.activity-text { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.activity-date { flex: none; color: var(--ink-faint); font-size: 11px; }
/* Fantasy team name + real owner name stacked, like a player's stat line
   underneath their name — everywhere a team name is a prominent label
   (owner's ask, 2026-09-14), whenever a manager is actually on record. */
.side-id { display: flex; flex-direction: column; min-width: 0; }
.side.right .side-id { align-items: flex-end; }
.side-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.side-owner, .mc-owner, .team-cell-owner, .header-owner { font-size: 10.5px; font-weight: 500; color: var(--ink-faint); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 100%; }
.team-cell { display: flex; align-items: center; gap: 8px; min-width: 0; }
.team-cell-id { display: flex; flex-direction: column; min-width: 0; }
.team-cell-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.team-cell.mine, .side.mine, .mc-team.mine { background: var(--accent-soft); border-radius: 8px; padding: 3px 8px; margin: -3px -8px; }
.mp.mine { background: var(--accent-soft); border-radius: 8px; padding: 4px 8px; margin: -4px -8px; }
/* Every scoreboard matchup is clickable — opens the same position-aligned
   comparison used for "my matchup" on Home, but for any two managers
   (owner's explicit ask, 2026-09-14: "see the live scoring between all
   managers", not just their own). */
/* An author `display` rule always beats the UA stylesheet's default
   `[hidden]{display:none}`, regardless of selector specificity — so
   .modal-overlay's own `display:flex` was silently winning over the
   `hidden` attribute closeMatchupModal() sets, leaving an empty opaque
   panel stuck on screen after the first close. The `[hidden]` rule below
   needs to come from author CSS too, and after the base rule so it wins. */
.modal-overlay { position: fixed; inset: 0; background: rgba(5,3,12,0.78); backdrop-filter: blur(3px); z-index: 300; display: flex; align-items: flex-start; justify-content: center; padding: 40px 16px; overflow-y: auto; }
.modal-overlay[hidden] { display: none; }
/* .card's own background is a ~4.5% translucent overlay, meant to sit on
   the page's solid ground — stacked on the modal backdrop instead, the
   page behind it was still bleeding through and washing out the stat
   text. Force a fully opaque panel here so the modal reads cleanly no
   matter what's behind it. */
.modal-box { position: relative; width: 100%; max-width: 640px; padding: 26px 28px; background: var(--sidebar); box-shadow: 0 24px 60px rgba(0,0,0,0.5); }
.modal-close { position: absolute; top: 14px; right: 14px; width: 30px; height: 30px; border-radius: 50%; border: none; background: var(--card-2); color: var(--ink); font-size: 15px; cursor: pointer; display: flex; align-items: center; justify-content: center; }
.modal-close:hover { background: var(--accent-soft); color: var(--accent); }
.logo { width: 22px; height: 22px; border-radius: 50%; object-fit: cover; vertical-align: middle; margin-right: 6px; background: var(--card-2); }

/* --- head-to-head matchup comparison (Home) --- */
.matchup-grid { gap: 20px; }
.matchup-card { padding: 26px 28px; }
.mc-league-label { font-size: 12px; font-weight: 700; color: var(--ink-faint); text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 14px; }
.matchup-card-head { display: flex; align-items: center; gap: 12px; padding-bottom: 8px; }
.mc-team { display: flex; align-items: center; gap: 10px; flex: 1 1 0; min-width: 0; overflow: hidden; }
.mc-team.right { flex-direction: row-reverse; text-align: right; }
.mc-team-id { display: flex; flex-direction: column; min-width: 0; }
.mc-team.right .mc-team-id { align-items: flex-end; }
.mc-name { font-weight: 800; font-size: 16px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; display: block; min-width: 0; }
.mc-score { flex: none; font-size: 30px; font-weight: 800; font-variant-numeric: tabular-nums; text-align: center; white-space: nowrap; padding: 0 8px; }
.mc-dash { color: var(--ink-faint); font-weight: 500; margin: 0 5px; }
.mc-live-row { text-align: center; margin: -4px 0 14px; }
.matchup-divider { height: 1px; background: var(--border); margin: 6px 0 14px; }
.matchup-row { display: grid; grid-template-columns: 1fr 56px 1fr; align-items: center; gap: 12px; padding: 9px 0; font-size: 14.5px; border-bottom: 1px solid rgba(255,255,255,0.04); }
.matchup-row:last-child { border-bottom: none; }
.mp { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
/* space-between pushes points toward the shared center slot column (like
   ESPN's own matchup card), keeping the name pinned to the outer edge —
   .mp-id groups name+injury-badge into one flex item so they move
   together instead of space-between prying them apart too. */
.mp-main { display: flex; align-items: center; gap: 6px; min-width: 0; justify-content: space-between; }
.mp-mine { text-align: left; }
.mp-theirs { text-align: right; }
.mp-id { display: flex; align-items: center; gap: 6px; min-width: 0; overflow: hidden; }
.mp-theirs .mp-id { flex-direction: row-reverse; }
.mp-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 600; }
.mp-pts { font-weight: 800; font-variant-numeric: tabular-nums; flex: none; min-width: 34px; }
.mp-sub { font-size: 10px; color: var(--ink-faint); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.mp-slot { text-align: center; font-size: 10.5px; font-weight: 800; color: var(--ink-faint); text-transform: uppercase; letter-spacing: 0.04em; }
/* Three real states from raw_pro_games, not just played/not-played:
   not_started (their game hasn't kicked off — points is null, no upside
   spent yet), live (game in progress — points can still change), final
   (settled). Dim not-started, pulse a dot on live, leave final plain. */
.mp.not-played { opacity: 0.42; }
.mp.not-played .mp-pts { font-weight: 600; }
.mp.live-game .mp-pts { color: var(--pink-a); }
.live-dot { display: inline-block; width: 6px; height: 6px; border-radius: 50%; background: var(--pink-a); animation: livedot 1.4s ease-in-out infinite; flex: none; }
@keyframes livedot { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }
/* Injury status — real values from ESPN's mRoster player.injuryStatus,
   captured daily into raw_player_snapshots (previously an unused table).
   Amber for still-probable-to-play, pink for likely/certainly out. */
.inj-badge { font-size: 8.5px; font-weight: 800; padding: 1px 4px; border-radius: 4px; flex: none; letter-spacing: 0.02em; }
.inj-badge.inj-q { background: rgba(247,195,88,0.18); color: var(--amber-a); }
.inj-badge.inj-o { background: rgba(241,88,163,0.18); color: var(--pink-a); }
.roster-row { display: flex; align-items: center; gap: 8px; padding: 6px 0; border-bottom: 1px solid var(--border); font-size: 12.5px; }
.roster-row:last-child { border-bottom: none; }
.roster-row.bench { opacity: 0.55; }
.roster-row.not-played { opacity: 0.55; }
.roster-row.live-game .pts { color: var(--pink-a); }
.roster-row .name { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.roster-row .name-main { display: flex; align-items: center; gap: 6px; min-width: 0; }
.roster-row .name-main span:first-child { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.roster-row .sub { font-size: 10.5px; color: var(--ink-faint); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.roster-row .pts { font-weight: 800; font-variant-numeric: tabular-nums; flex: none; }
select { background: var(--card-2); color: var(--ink); border: 1px solid var(--border); border-radius: 8px; padding: 7px 10px; font-size: 13px; }
.footer { text-align: center; color: var(--ink-faint); font-size: 11px; padding: 20px; }

/* --- bar list (horizontal) --- */
.barlist-row { display: flex; align-items: center; gap: 10px; margin-bottom: 9px; font-size: 12px; }
.barlist-row .bl-label { width: 108px; flex: none; color: var(--ink-soft); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.barlist-row .bl-track { flex: 1; height: 8px; border-radius: 999px; background: rgba(255,255,255,0.06); overflow: hidden; }
.barlist-row .bl-fill { height: 100%; border-radius: 999px; }
.barlist-row .bl-val { width: 38px; flex: none; text-align: right; font-weight: 700; font-variant-numeric: tabular-nums; }

"""

JS = """
let currentLeague = Object.keys(DIGEST.leagues)[0];
let currentTab = 'home';

// The page auto-reloads every few minutes during live-refresh mode (see
// <meta http-equiv="refresh">) to pick up the freshly-regenerated file.
// Without this, that reload would silently dump you back to Home/the first
// league every time. Wrapped in try/catch — localStorage can throw in some
// contexts (e.g. certain private-browsing modes) and this is a convenience,
// never something the page should break over.
const VIEW_STATE_KEY = 'espn-ffl-view-state';
function saveViewState() {
  try { localStorage.setItem(VIEW_STATE_KEY, JSON.stringify({ tab: currentTab, league: currentLeague })); } catch (e) {}
}
function restoreViewState() {
  try {
    const raw = localStorage.getItem(VIEW_STATE_KEY);
    if (!raw) return;
    const state = JSON.parse(raw);
    if (state.league && DIGEST.leagues[state.league]) currentLeague = state.league;
    if (state.tab && document.getElementById('page-' + state.tab)) currentTab = state.tab;
  } catch (e) {}
}

function el(tag, cls, html) { const e = document.createElement(tag); if (cls) e.className = cls; if (html !== undefined) e.innerHTML = html; return e; }
function fmtPct(v) { return v === null || v === undefined ? '—' : (v * 100).toFixed(1) + '%'; }
function logoImg(leagueId, teamId, size) {
  const b64 = DIGEST.team_logos[leagueId + '_' + teamId];
  size = size || 22;
  return b64 ? `<img class="logo" style="width:${size}px;height:${size}px" src="${b64}">` : `<span class="logo" style="width:${size}px;height:${size}px;display:inline-flex;align-items:center;justify-content:center;font-size:10px">?</span>`;
}

function switchLeague(lid) {
  currentLeague = lid;
  document.querySelectorAll('.league-switch button').forEach(b => b.classList.toggle('active', b.dataset.lid === lid));
  saveViewState();
  renderCurrentTab();
}
function switchTab(tab) {
  currentTab = tab;
  document.querySelectorAll('.navitem').forEach(t => t.classList.toggle('active', t.dataset.tab === tab));
  document.querySelectorAll('.page').forEach(p => p.classList.toggle('active', p.id === 'page-' + tab));
  saveViewState();
  renderCurrentTab();
  closeNav();
}

function openNav() {
  document.getElementById('sidebar').classList.add('open');
  document.getElementById('nav-backdrop').classList.add('open');
}
function closeNav() {
  document.getElementById('sidebar').classList.remove('open');
  document.getElementById('nav-backdrop').classList.remove('open');
}
function toggleNav() {
  document.getElementById('sidebar').classList.contains('open') ? closeNav() : openNav();
}
function renderCurrentTab() {
  const root = document.getElementById('page-' + currentTab);
  if (!root) return;
  ({ home: renderHome, myteam: renderMyTeam, league: renderLeague, managers: renderManagers, analytics: renderAnalytics })[currentTab](root);
}

/* ---------- reusable chart components, all driven by real numbers ---------- */

function ringChart(pct, colorA, colorB, size) {
  size = size || 108;
  const stroke = 10;
  const r = size / 2 - stroke;
  const c = 2 * Math.PI * r;
  const clamped = Math.max(0, Math.min(1, pct === null || pct === undefined ? 0 : pct));
  const dash = c * clamped;
  const gid = 'rg' + Math.random().toString(36).slice(2, 9);
  return `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">
    <defs><linearGradient id="${gid}" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="${colorA}"/><stop offset="100%" stop-color="${colorB}"/>
    </linearGradient></defs>
    <circle cx="${size/2}" cy="${size/2}" r="${r}" fill="none" stroke="var(--ring-track)" stroke-width="${stroke}"/>
    <circle cx="${size/2}" cy="${size/2}" r="${r}" fill="none" stroke="url(#${gid})" stroke-width="${stroke}" stroke-linecap="round"
      stroke-dasharray="${dash} ${c}" transform="rotate(-90 ${size/2} ${size/2})"/>
  </svg>`;
}

function ringWithLabel(pct, colorA, colorB, valueText, subLabel, size) {
  size = size || 108;
  const ring = ringChart(pct, colorA, colorB, size);
  const innerWidth = Math.round(size * 0.62);
  return `<div style="position:relative;display:inline-flex;align-items:center;justify-content:center">
    ${ring}
    <div style="position:absolute;text-align:center;width:${innerWidth}px">
      <div style="font-size:${size >= 100 ? 17 : 14}px;font-weight:800;line-height:1.1">${valueText}</div>
      ${subLabel ? `<div style="font-size:8.5px;color:var(--ink-soft);line-height:1.2;margin-top:2px">${subLabel}</div>` : ''}
    </div>
  </div>`;
}

function barList(rows, colorA, colorB) {
  const max = Math.max(1, ...rows.map(r => r.value));
  return rows.map(r => `
    <div class="barlist-row">
      <div class="bl-label">${r.label}</div>
      <div class="bl-track"><div class="bl-fill" style="width:${(Math.max(0,r.value)/max*100).toFixed(1)}%;background:linear-gradient(90deg, ${colorA}, ${colorB})"></div></div>
      <div class="bl-val">${r.value.toFixed(1)}</div>
    </div>`).join('');
}

/* ---------------------------------------------------------------------- */

function matchRow(lg, m) {
  const L = DIGEST.leagues[lg];
  const mgrA = teamManager(L, m.a.team_id), mgrB = teamManager(L, m.b.team_id);
  const aMine = m.a.team_id === L.my_team_id, bMine = m.b.team_id === L.my_team_id;
  return `<div class="match-row" onclick="openMatchupModal('${lg}', ${m.a.team_id}, ${m.b.team_id}, ${m.a.score}, ${m.b.score}, ${m.live ? 'true' : 'false'})">
    <div class="side${aMine ? ' mine' : ''}">${logoImg(lg, m.a.team_id)}<div class="side-id"><span class="side-name">${m.a.name}</span>${mgrA ? `<span class="side-owner">${mgrA}</span>` : ''}</div></div>
    <div class="score">${m.a.score.toFixed(1)} - ${m.b.score.toFixed(1)} ${m.live ? '<span class="badge live">LIVE</span>' : ''}</div>
    <div class="side right${bMine ? ' mine' : ''}"><div class="side-id"><span class="side-name">${m.b.name}</span>${mgrB ? `<span class="side-owner">${mgrB}</span>` : ''}</div>${logoImg(lg, m.b.team_id)}</div>
  </div>`;
}

function cardHead(iconName, title, subtitle) {
  const titleHtml = subtitle
    ? `<span class="card-head-title"><span>${title}</span><span class="header-owner">${subtitle}</span></span>`
    : title;
  return `<div class="card-head"><h2><span class="icon-chip">${ICON_SVG[iconName]}</span>${titleHtml}</h2></div>`;
}

// Confirmed live, Phase 1 (2026-09-13) — a roster SLOT scheme, not a
// player's real position (see CLAUDE.md rule 7). Used only for display
// labels here; storage keeps lineup_slot_id and default_position_id
// separate on purpose.
const SLOT_LABELS = { 0: 'QB', 2: 'RB', 4: 'WR', 6: 'TE', 16: 'D/ST', 17: 'K', 20: 'BE', 21: 'IR', 23: 'FLEX' };

function findMyMatchup(L) {
  const m = L.this_week.matchups.find(x => x.a.team_id === L.my_team_id || x.b.team_id === L.my_team_id);
  if (!m) return null;
  const mine = m.a.team_id === L.my_team_id ? m.a : m.b;
  const opp = m.a.team_id === L.my_team_id ? m.b : m.a;
  return { mine, opp, live: m.live };
}

function statusClass(status) {
  if (status === 'live') return ' live-game';
  if (status === 'not_started' || status === 'bye') return ' not-played';
  return '';
}
function liveDot(status) { return status === 'live' ? '<span class="live-dot" title="Game in progress"></span>' : ''; }

const INJ_LABELS = { QUESTIONABLE: ['Q', 'q'], DOUBTFUL: ['D', 'o'], OUT: ['O', 'o'], INJURY_RESERVE: ['IR', 'o'], DAY_TO_DAY: ['DTD', 'q'], SUSPENSION: ['SUSP', 'o'] };
function injBadge(status) {
  if (!status) return '';
  const [label, sev] = INJ_LABELS[status] || [status.slice(0, 3), 'q'];
  return `<span class="inj-badge inj-${sev}" title="${status}">${label}</span>`;
}
function gameLine(p) {
  if (p.game_status === 'bye') return 'BYE';
  if (!p.opponent) return '';
  const prefix = p.is_home ? '' : '@';
  if (p.game_status === 'not_started') {
    const when = p.kickoff_utc ? new Date(p.kickoff_utc).toLocaleString(undefined, { weekday: 'short', hour: 'numeric', minute: '2-digit' }) : '';
    return `${prefix}${p.opponent} ${when}`.trim();
  }
  const score = (p.own_score != null && p.opp_score != null) ? `${p.own_score.toFixed(0)}-${p.opp_score.toFixed(0)} ` : '';
  return `${prefix}${p.opponent} ${score}${p.game_detail || ''}`.trim();
}
// Two separate lines under a player, matching the real ESPN matchup
// card: the game's schedule/live score first, the real stat line below
// it (when they've actually recorded stats yet) — not one-or-the-other.
function subLines(p) { return [gameLine(p), p.stat_line].filter(Boolean); }
function subLinesHtml(p, cls) { return subLines(p).map(l => `<div class="${cls}">${l}</div>`).join(''); }

function teamName(L, teamId) {
  const t = L.teams.find(t => t.team_id === teamId);
  return t ? t.team_name : '';
}
function teamManager(L, teamId) {
  const t = L.teams.find(t => t.team_id === teamId);
  return t && t.manager ? t.manager : '';
}
// One league pink, the other purple (owner's ask, 2026-09-14) — a
// consistent accent so the two side-by-side leagues on Home are tellable
// apart at a glance without reading. First league in DIGEST.leagues
// (insertion order, matches config.LEAGUES) is pink, second is purple;
// used on every card that belongs to one league, plus the league-switch
// pill (build_html, Python side — kept in sync with this same convention).
function leagueAccentClass(leagueId) {
  return Object.keys(DIGEST.leagues).indexOf(leagueId) === 0 ? 'league-pink' : 'league-purple';
}
// Real owner name under a fantasy team name, wherever the team name is a
// prominent label — same idea as a player's stat line underneath their
// name (owner's ask, 2026-09-14). Omitted whenever no manager is on
// record (an orphaned/auto-drafted team), never fabricated.
function teamCellHtml(logoHtml, name, manager) {
  return `<div class="team-cell">${logoHtml}<div class="team-cell-id"><span class="team-cell-name">${name}</span>${manager ? `<span class="team-cell-owner">${manager}</span>` : ''}</div></div>`;
}

// Position-aligned rows for any two teams in a league/week — group each
// side's starters by lineup slot, then pair them up slot-instance by
// slot-instance (e.g. RB1 vs RB1, RB2 vs RB2), same idea as ESPN's own
// side-by-side matchup view. Shared by "my matchup" on Home and the
// click-through modal for every other matchup on the scoreboard.
function matchupRowsHtml(leagueId, teamAId, teamBId) {
  const L = DIGEST.leagues[leagueId];
  // Which side (if either) is actually the owner's own team — teamAId is
  // always "mine" when called from matchupComparisonCard, but this same
  // function also renders the generic click-through modal for any two
  // OTHER managers, where neither side is mine. Computed here rather than
  // assumed from position, so the "mine" player tint (owner's ask,
  // 2026-09-14: same tactic as the team-name highlight, applied to every
  // player on my roster during a matchup) only ever lights up for real.
  const aIsMe = teamAId === L.my_team_id, bIsMe = teamBId === L.my_team_id;
  const aDetail = L.teams_detail[String(teamAId)];
  const bDetail = L.teams_detail[String(teamBId)];
  const aStarters = (aDetail ? aDetail.roster : []).filter(p => p.is_starter);
  const bStarters = (bDetail ? bDetail.roster : []).filter(p => p.is_starter);

  const bySlot = (players) => players.reduce((acc, p) => { (acc[p.slot_id] = acc[p.slot_id] || []).push(p); return acc; }, {});
  const aSlots = bySlot(aStarters), bSlots = bySlot(bStarters);
  const allSlotIds = [...new Set([...Object.keys(aSlots), ...Object.keys(bSlots)])]
    .sort((x, y) => x - y);

  let rows = '';
  allSlotIds.forEach(slotId => {
    const mine = aSlots[slotId] || [], theirs = bSlots[slotId] || [];
    const count = Math.max(mine.length, theirs.length);
    for (let i = 0; i < count; i++) {
      const mp = mine[i], op = theirs[i];
      const mineHtml = mp ? `
        <div class="mp-main"><span class="mp-id"><span class="mp-name">${mp.name}</span>${injBadge(mp.injury_status)}</span><span class="mp-pts">${liveDot(mp.game_status)}${mp.points === null ? '—' : mp.points.toFixed(1)}</span></div>
        ${subLinesHtml(mp, 'mp-sub')}` : '<span class="muted">—</span>';
      const theirsHtml = op ? `
        <div class="mp-main"><span class="mp-pts">${op.points === null ? '—' : op.points.toFixed(1)}${liveDot(op.game_status)}</span><span class="mp-id">${injBadge(op.injury_status)}<span class="mp-name">${op.name}</span></span></div>
        ${subLinesHtml(op, 'mp-sub')}` : '<span class="muted">—</span>';
      rows += `<div class="matchup-row">
        <div class="mp mp-mine${aIsMe ? ' mine' : ''}${mp ? statusClass(mp.game_status) : ''}">${mineHtml}</div>
        <div class="mp-slot">${SLOT_LABELS[slotId] || slotId}</div>
        <div class="mp mp-theirs${bIsMe ? ' mine' : ''}${op ? statusClass(op.game_status) : ''}">${theirsHtml}</div>
      </div>`;
    }
  });
  return rows;
}

function matchupCompareHead(leagueId, teamAId, teamBId, nameA, nameB, scoreA, scoreB, live) {
  const L = DIGEST.leagues[leagueId];
  const mgrA = teamManager(L, teamAId), mgrB = teamManager(L, teamBId);
  const aMine = teamAId === L.my_team_id, bMine = teamBId === L.my_team_id;
  return `
    <div class="matchup-card-head">
      <div class="mc-team${aMine ? ' mine' : ''}">${logoImg(leagueId, teamAId, 26)}<div class="mc-team-id"><span class="mc-name">${nameA}</span>${mgrA ? `<span class="mc-owner">${mgrA}</span>` : ''}</div></div>
      <div class="mc-score">${scoreA.toFixed(1)}<span class="mc-dash">–</span>${scoreB.toFixed(1)}</div>
      <div class="mc-team right${bMine ? ' mine' : ''}"><div class="mc-team-id"><span class="mc-name">${nameB}</span>${mgrB ? `<span class="mc-owner">${mgrB}</span>` : ''}</div>${logoImg(leagueId, teamBId, 26)}</div>
    </div>
    ${live ? '<div class="mc-live-row"><span class="badge live">LIVE</span></div>' : ''}
    <div class="matchup-divider"></div>`;
}

function matchupComparisonCard(leagueId) {
  const L = DIGEST.leagues[leagueId];
  const matchup = findMyMatchup(L);
  const card = el('div', `card matchup-card ${leagueAccentClass(leagueId)}`);
  if (!matchup) {
    card.innerHTML = cardHead('league', L.name) + '<p class="muted">No matchup this week (bye).</p>';
    return card;
  }
  card.innerHTML = `
    <div class="mc-league-label">${L.name}</div>
    ${matchupCompareHead(leagueId, matchup.mine.team_id, matchup.opp.team_id, L.my_team_name, matchup.opp.name, matchup.mine.score, matchup.opp.score, matchup.live)}
    ${matchupRowsHtml(leagueId, matchup.mine.team_id, matchup.opp.team_id)}
  `;
  return card;
}

function openMatchupModal(leagueId, teamAId, teamBId, scoreA, scoreB, live) {
  const L = DIGEST.leagues[leagueId];
  const box = document.querySelector('.modal-box');
  box.classList.remove('league-pink', 'league-purple');
  box.classList.add(leagueAccentClass(leagueId));
  document.getElementById('matchup-modal-content').innerHTML = `
    <div class="mc-league-label">${L.name}</div>
    ${matchupCompareHead(leagueId, teamAId, teamBId, teamName(L, teamAId), teamName(L, teamBId), scoreA, scoreB, live)}
    ${matchupRowsHtml(leagueId, teamAId, teamBId)}
  `;
  document.getElementById('matchup-modal').hidden = false;
  document.body.style.overflow = 'hidden';
}
function closeMatchupModal(evt) {
  if (evt && evt.target !== evt.currentTarget) return;
  document.getElementById('matchup-modal').hidden = true;
  document.body.style.overflow = '';
}

function activityDate(iso) {
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}
function activityRowHtml(a) {
  const when = activityDate(a.proposed_at);
  if (a.kind === 'trade') {
    const text = a.sides.map(s => `<b>${s.manager || s.team_name}</b> got ${s.received.join(', ')}`).join(' · ');
    return `<div class="activity-row"><div class="activity-main"><span class="activity-tag trade">Trade</span><span class="activity-text">${text}</span></div><div class="activity-date">${when}</div></div>`;
  }
  const who = a.manager || a.team_name;
  const parts = [];
  if (a.adds.length) parts.push(`added ${a.adds.join(', ')}`);
  if (a.drops.length) parts.push(`dropped ${a.drops.join(', ')}`);
  const tag = a.kind === 'waiver' ? 'Waiver' : 'Free agent';
  return `<div class="activity-row"><div class="activity-main"><span class="activity-tag ${a.kind}">${tag}</span><span class="activity-text"><b>${who}</b> ${parts.join(', ')}</span></div><div class="activity-date">${when}</div></div>`;
}
function activityCard(leagueId) {
  const L = DIGEST.leagues[leagueId];
  const card = el('div', `card ${leagueAccentClass(leagueId)}`);
  card.innerHTML = cardHead('trend', `${L.name} — Recent activity`) +
    (L.activity.length ? L.activity.map(activityRowHtml).join('') : '<p class="muted">No waiver, free-agent, or trade activity yet.</p>');
  return card;
}

function renderHome(root) {
  root.innerHTML = '';

  // Home shows both leagues, always, regardless of the league switcher
  // (owner's explicit call, 2026-09-14) — the switcher only affects the
  // other single-team-scoped tabs (My Team/League/Managers/Analytics).
  // Three sections, both side by side per league: your own matchup
  // (position-by-position vs. this week's opponent), the full league
  // scoreboard, then a real activity feed — so the owner doesn't have to
  // open the ESPN app to see who moved (owner's ask, 2026-09-14).
  const leagueIds = Object.keys(DIGEST.leagues);

  const bothMatchups = el('div', 'grid grid-2 matchup-grid');
  leagueIds.forEach(lid => bothMatchups.appendChild(matchupComparisonCard(lid)));
  root.appendChild(bothMatchups);

  const bothFixtures = el('div', 'grid grid-2');
  leagueIds.forEach(lid => {
    const L = DIGEST.leagues[lid];
    const card = el('div', `card ${leagueAccentClass(lid)}`);
    card.innerHTML = cardHead('league', `${L.name} — Week ${L.this_week.week} matchups`);
    L.this_week.matchups.forEach(m => card.appendChild(el('div', null, matchRow(lid, m))));
    bothFixtures.appendChild(card);
  });
  root.appendChild(bothFixtures);

  const bothActivity = el('div', 'grid grid-2');
  leagueIds.forEach(lid => bothActivity.appendChild(activityCard(lid)));
  root.appendChild(bothActivity);
}

function renderTeamDetail(container, detail, leagueId) {
  container.innerHTML = '';
  if (!detail || !detail.season_stats) { container.appendChild(el('p', 'muted', 'No data yet.')); return; }
  const s = detail.season_stats, w = detail.week_stats;

  const kpis = el('div', 'kpi-row');
  kpis.innerHTML = `
    <div class="kpi amber"><div class="value">${s.record.w}-${s.record.l}-${s.record.t}</div><div class="label">Record</div></div>
    <div class="kpi blue"><div class="value">${s.points_for.toFixed(1)}</div><div class="label">Points for</div></div>
    <div class="kpi cyan"><div class="value">${fmtPct(s.lineup_efficiency)}</div><div class="label">Lineup efficiency ${s.is_provisional ? '<span class="badge prov">early</span>' : ''}</div></div>
    <div class="kpi pink"><div class="value">${s.total_bench_points.toFixed(1)}</div><div class="label">Bench points</div></div>
  `;
  container.appendChild(kpis);

  if (w) {
    const wCard = el('div', 'card');
    wCard.innerHTML = cardHead('trend', 'This week') +
      `<div style="display:flex;align-items:center;gap:18px;flex-wrap:wrap">
        ${ringWithLabel(w.efficiency, 'var(--cyan-a)', 'var(--cyan-b)', fmtPct(w.efficiency), null, 92)}
        <p class="muted">Actual ${w.actual_points.toFixed(1)} / optimal ${w.optimal_points.toFixed(1)} — rank ${w.rank} of ${DIGEST.leagues[leagueId].teams.length}</p>
      </div>`;
    container.appendChild(wCard);
  }

  const rosterCard = el('div', 'card');
  rosterCard.appendChild(el('div', null, cardHead('myteam', 'Roster')));
  const starters = detail.roster.filter(p => p.is_starter);
  const bench = detail.roster.filter(p => !p.is_starter);
  const rosterRowHtml = p => `<div class="name"><div class="name-main"><span>${p.name}</span>${injBadge(p.injury_status)}</div>${subLinesHtml(p, 'sub')}</div><div class="pts">${liveDot(p.game_status)}${p.points === null ? '—' : p.points.toFixed(1)}</div>`;
  starters.forEach(p => rosterCard.appendChild(el('div', 'roster-row' + statusClass(p.game_status), rosterRowHtml(p))));
  if (bench.length) {
    rosterCard.appendChild(el('div', 'muted', 'Bench'));
    bench.forEach(p => rosterCard.appendChild(el('div', 'roster-row bench' + statusClass(p.game_status), rosterRowHtml(p))));
  }
  container.appendChild(rosterCard);
}

function renderMyTeam(root) {
  const L = DIGEST.leagues[currentLeague];
  root.innerHTML = `<div class="card">${cardHead('myteam', L.my_team_name, teamManager(L, L.my_team_id))}</div>`;
  const wrap = el('div');
  renderTeamDetail(wrap, L.my_team_detail, currentLeague);
  root.appendChild(wrap);

  if (L.waiver_moves.length) {
    const wCard = el('div', 'card');
    wCard.innerHTML = cardHead('trend', 'Waiver moves') + `<table><thead><tr><th>Week</th><th>Added</th><th>Dropped</th><th>Net (${L.waiver_moves[0].horizon_weeks}wk)</th></tr></thead><tbody>
      ${L.waiver_moves.map(m => `<tr><td>${m.week}</td><td>${m.added}</td><td>${m.dropped || '—'}</td><td>${m.is_complete ? (m.net === null ? '—' : m.net.toFixed(1)) : 'incomplete'}</td></tr>`).join('')}
    </tbody></table>`;
    root.appendChild(wCard);
  }
}

function renderLeague(root) {
  const L = DIGEST.leagues[currentLeague];
  root.innerHTML = `<div class="card">${cardHead('league', `Standings — after Week ${L.this_week.week}`)}<table><thead><tr><th>#</th><th>Team</th><th>W-L-T</th><th>PF</th><th>PA</th></tr></thead><tbody>
    ${L.standings.map((s,i) => `<tr class="${s.is_owner ? 'owner-row' : ''}"><td>${i+1}</td><td>${teamCellHtml(logoImg(currentLeague, s.team_id), s.team_name, s.manager)}</td><td>${s.wins}-${s.losses}-${s.ties}</td><td>${s.points_for.toFixed(1)}</td><td>${s.points_against.toFixed(1)}</td></tr>`).join('')}
  </tbody></table></div>`;
  const mCard = el('div', 'card');
  mCard.innerHTML = cardHead('league', `Week ${L.this_week.week} matchups`);
  L.this_week.matchups.forEach(m => mCard.appendChild(el('div', null, matchRow(currentLeague, m))));
  root.appendChild(mCard);
}

function renderManagers(root) {
  const L = DIGEST.leagues[currentLeague];
  root.innerHTML = '';
  const selectCard = el('div', 'card');
  const select = el('select');
  L.teams.forEach(t => select.appendChild(new Option(t.team_name + (t.manager ? ' (' + t.manager + ')' : ''), t.team_id)));
  select.value = L.my_team_id;
  selectCard.innerHTML = cardHead('managers', 'Managers');
  selectCard.appendChild(select);
  root.appendChild(selectCard);

  const detailWrap = el('div');
  root.appendChild(detailWrap);

  function update() {
    renderTeamDetail(detailWrap, L.teams_detail[select.value], currentLeague);
  }
  select.addEventListener('change', update);
  update();
}

function renderAnalytics(root) {
  const L = DIGEST.leagues[currentLeague];
  root.innerHTML = '';
  const barCard = el('div', 'card');
  barCard.innerHTML = cardHead('analytics', 'Lineup efficiency leaderboard') +
    barList(L.leaderboard.map(t => ({ label: t.team_name, value: (t.lineup_efficiency || 0) * 100 })), 'var(--amber-a)', 'var(--amber-b)');
  root.appendChild(barCard);

  const tblCard = el('div', 'card');
  tblCard.innerHTML = `<table><thead><tr><th>Team</th><th>Efficiency</th><th>Bench pts</th></tr></thead><tbody>
    ${L.leaderboard.map(t => `<tr class="${t.team_id === L.my_team_id ? 'owner-row' : ''}"><td>${teamCellHtml(logoImg(currentLeague, t.team_id), t.team_name, t.manager)}</td><td>${fmtPct(t.lineup_efficiency)}</td><td>${t.bench_points.toFixed(1)}</td></tr>`).join('')}
  </tbody></table>
  <p class="muted">Luck index, power rankings, and playoff odds unlock at 5 and 7 weeks played (owner-confirmed gates) — insufficient sample right now.</p>`;
  root.appendChild(tblCard);
}

document.addEventListener('DOMContentLoaded', () => {
  restoreViewState();
  document.querySelectorAll('.league-switch button').forEach(b => b.classList.toggle('active', b.dataset.lid === currentLeague));
  document.querySelectorAll('.navitem').forEach(t => t.classList.toggle('active', t.dataset.tab === currentTab));
  document.querySelectorAll('.page').forEach(p => p.classList.toggle('active', p.id === 'page-' + currentTab));
  renderCurrentTab();
});
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeMatchupModal(); });
"""


def build_html(digest: dict) -> str:
    league_buttons = "".join(
        # First league pink, second purple — same convention as
        # leagueAccentClass() in JS, kept in sync by hand since this is
        # the one place the mapping is built server-side instead.
        f'<button data-lid="{lid}" class="{"active" if i == 0 else ""} {"league-pink" if i == 0 else "league-purple"}" onclick="switchLeague(\'{lid}\')">{l["name"]}</button>'
        for i, (lid, l) in enumerate(digest["leagues"].items())
    )
    tabs = [
        ("home", "Home", "home"), ("myteam", "My Team", "myteam"), ("league", "League", "league"),
        ("managers", "Managers", "managers"), ("analytics", "Analytics", "analytics"),
    ]
    nav_items = "".join(
        f'<div class="navitem {"active" if i == 0 else ""}" data-tab="{t}" onclick="switchTab(\'{t}\')">{icon(ic)}<span>{label}</span></div>'
        for i, (t, label, ic) in enumerate(tabs)
    )
    pages = "".join(f'<div class="page {"active" if i == 0 else ""}" id="page-{t}"></div>' for i, (t, _, _) in enumerate(tabs))

    owner_name = next((t["manager"] for l in digest["leagues"].values() for t in l["teams"] if t["is_owner"]), "Owner")
    initials = "".join(w[0] for w in owner_name.split()[:2]).upper() or "?"

    icon_svg_map = json.dumps({name: icon(name, 16) for name in ICONS})

    digest_json = json.dumps(digest)
    refresh_seconds = config.LIVE_REFRESH_SECONDS
    refresh_minutes = refresh_seconds / 60

    return f"""<meta charset="utf-8">
<meta http-equiv="refresh" content="{refresh_seconds}">
<title>Fantasy Football — Multi-League Dashboard</title>
<style>{CSS}</style>
<div class="shell">
  <div class="nav-backdrop" id="nav-backdrop" onclick="closeNav()"></div>
  <div class="sidebar" id="sidebar">
    <div class="brand">
      <span>Fantasy Football<span class="brand-sub">{digest['season_year']} season · Week {list(digest['leagues'].values())[0]['current_week']}</span></span>
      <button class="nav-close" onclick="closeNav()" aria-label="Close menu">{icon('close', 20)}</button>
    </div>
    {nav_items}
  </div>
  <main>
    <div class="topbar">
      <div class="topbar-left">
        <button class="hamburger-btn" onclick="toggleNav()" aria-label="Open menu">{icon('menu', 20)}</button>
        <div class="topbar-brand">Fantasy Football<span class="brand-sub">Week {list(digest['leagues'].values())[0]['current_week']}</span></div>
      </div>
      <div class="league-switch">{league_buttons}</div>
      <div class="topbar-icons">
        <div class="refresh-note" title="This page reloads itself automatically. It only shows new scores if src/live_refresh.py is running in the background — otherwise it's a harmless reload of the same file.">Auto-refresh every {refresh_minutes:g}m</div>
        <div class="icon-btn">{icon('bell')}<span class="dot"></span></div>
        <div class="profile-chip"><div class="avatar">{initials}</div><div><div class="name">{owner_name}</div><div class="role">League owner</div></div></div>
      </div>
    </div>
    <div class="scroll-area">
      <div class="content">{pages}</div>
      <div class="footer">Generated {digest['generated_at']} · Fact = stored raw data. Computed = derived by a documented formula. See CLAUDE.md.</div>
    </div>
  </main>
</div>
<div class="modal-overlay" id="matchup-modal" hidden onclick="closeMatchupModal(event)">
  <div class="card modal-box" onclick="event.stopPropagation()">
    <button class="modal-close" onclick="closeMatchupModal()" aria-label="Close">{icon('close', 16)}</button>
    <div id="matchup-modal-content"></div>
  </div>
</div>
<script>const DIGEST = {digest_json}; const ICON_SVG = {icon_svg_map};</script>
<script>{JS}</script>
"""


def run() -> int:
    print("Phase 7 — building dashboard.html\n")
    digest_path = config.DIGEST_DIR / "season.json"
    if not digest_path.exists():
        print("FAILED: digest/season.json not found — run `python -m src.digest` first.")
        return 1
    digest = json.loads(digest_path.read_text())
    html = build_html(digest)
    out_path = config.REPO_ROOT / "dashboard.html"
    out_path.write_text(html)
    print(f"Wrote {out_path} ({out_path.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(run())
