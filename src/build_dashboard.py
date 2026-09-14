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

/* --- sidebar --- */
.sidebar { width: 216px; flex: none; background: var(--sidebar); border-right: 1px solid var(--border); padding: 20px 14px; display: flex; flex-direction: column; gap: 4px; height: 100vh; overflow-y: auto; }
.sidebar .brand { font-weight: 800; font-size: 15px; letter-spacing: -0.01em; padding: 6px 10px 18px; }
.sidebar .brand-sub { display: block; color: var(--ink-faint); font-size: 10.5px; font-weight: 500; margin-top: 3px; }
.navitem { display: flex; align-items: center; gap: 10px; padding: 10px 12px; border-radius: 11px; color: var(--ink-soft); font-size: 13px; font-weight: 700; cursor: pointer; }
.navitem svg { flex: none; opacity: 0.85; }
.navitem.active { background: linear-gradient(135deg, var(--blue-a), var(--blue-b)); color: #fff; }
.navitem.active svg { opacity: 1; }
.navitem:not(.active):hover { background: rgba(255,255,255,0.04); color: var(--ink); }
@media (max-width: 820px) {
  html, body { height: auto; overflow: visible; }
  .shell { flex-direction: column; height: auto; }
  .sidebar { width: 100%; height: auto; flex-direction: row; align-items: center; overflow-x: auto; overflow-y: hidden; padding: 10px 12px; gap: 6px; }
  .sidebar .brand { display: none; }
  .navitem { flex: none; white-space: nowrap; }
  main { height: auto; overflow: visible; }
  .scroll-area { overflow-y: visible; }
}

/* --- topbar --- */
.topbar { flex: none; display: flex; align-items: center; justify-content: space-between; gap: 14px; padding: 16px 24px; flex-wrap: wrap; border-bottom: 1px solid var(--border); }
.league-switch { display: flex; gap: 4px; background: var(--card); border: 1px solid var(--border); border-radius: 999px; padding: 4px; }
.league-switch button { border: none; background: transparent; color: var(--ink-soft); padding: 8px 16px; border-radius: 999px; font-size: 12.5px; font-weight: 700; cursor: pointer; }
.league-switch button.active { background: linear-gradient(135deg, var(--blue-a), var(--blue-b)); color: #fff; }
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
.card-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.card-head h2 { margin: 0; font-size: 13.5px; display: flex; align-items: center; gap: 8px; }
.card-head .icon-chip { width: 22px; height: 22px; border-radius: 7px; background: var(--accent-soft); color: var(--accent); display: flex; align-items: center; justify-content: center; }
.card h3 { margin: 0 0 8px; font-size: 11.5px; color: var(--ink-soft); text-transform: uppercase; letter-spacing: 0.05em; }

table { width: 100%; border-collapse: collapse; font-size: 13px; }
th, td { text-align: left; padding: 8px 8px; border-bottom: 1px solid var(--border); }
th { color: var(--ink-soft); font-weight: 700; font-size: 10.5px; text-transform: uppercase; letter-spacing: 0.04em; }
tr.owner-row td { background: var(--accent-soft); }
.muted { color: var(--ink-soft); font-size: 12px; }
.badge { display: inline-block; font-size: 9.5px; font-weight: 800; text-transform: uppercase; padding: 2px 7px; border-radius: 999px; }
.badge.live { background: rgba(241,88,163,0.16); color: var(--pink-a); }
.badge.prov { background: var(--accent-soft); color: var(--accent); }
.match-row { display: flex; align-items: center; gap: 10px; padding: 8px 0; border-bottom: 1px solid var(--border); font-size: 13px; }
.match-row:last-child { border-bottom: none; }
.match-row .side { flex: 1; font-weight: 700; }
.match-row .side.right { text-align: right; }
.match-row .score { min-width: 90px; text-align: center; font-weight: 800; font-variant-numeric: tabular-nums; }
.logo { width: 22px; height: 22px; border-radius: 50%; object-fit: cover; vertical-align: middle; margin-right: 6px; background: var(--card-2); }

/* --- head-to-head matchup comparison (Home) --- */
.mc-league-label { font-size: 10.5px; font-weight: 700; color: var(--ink-faint); text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 8px; }
.matchup-card-head { display: flex; align-items: center; gap: 8px; padding-bottom: 6px; }
.mc-team { display: flex; align-items: center; gap: 7px; flex: 1 1 0; min-width: 0; overflow: hidden; }
.mc-team.right { flex-direction: row-reverse; text-align: right; }
.mc-name { font-weight: 800; font-size: 12.5px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; display: block; min-width: 0; }
.mc-score { flex: none; font-size: 18px; font-weight: 800; font-variant-numeric: tabular-nums; text-align: center; white-space: nowrap; padding: 0 4px; }
.mc-dash { color: var(--ink-faint); font-weight: 500; margin: 0 3px; }
.mc-live-row { text-align: center; margin: -2px 0 10px; }
.matchup-divider { height: 1px; background: var(--border); margin: 4px 0 10px; }
.matchup-row { display: grid; grid-template-columns: 1fr 46px 1fr; align-items: center; gap: 8px; padding: 5px 0; font-size: 12px; }
.mp { display: flex; align-items: center; gap: 6px; min-width: 0; }
.mp-mine { justify-content: flex-start; }
.mp-theirs { justify-content: flex-end; text-align: right; }
.mp-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.mp-pts { font-weight: 800; font-variant-numeric: tabular-nums; flex: none; }
.mp-slot { text-align: center; font-size: 9.5px; font-weight: 800; color: var(--ink-faint); text-transform: uppercase; letter-spacing: 0.03em; }
.roster-row { display: flex; align-items: center; gap: 8px; padding: 6px 0; border-bottom: 1px solid var(--border); font-size: 12.5px; }
.roster-row:last-child { border-bottom: none; }
.roster-row.bench { opacity: 0.55; }
.roster-row .name { flex: 1; }
.roster-row .pts { font-weight: 800; font-variant-numeric: tabular-nums; }
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
  return `<div class="match-row">
    <div class="side">${logoImg(lg, m.a.team_id)}${m.a.name}</div>
    <div class="score">${m.a.score.toFixed(1)} - ${m.b.score.toFixed(1)} ${m.live ? '<span class="badge live">LIVE</span>' : ''}</div>
    <div class="side right">${m.b.name}${logoImg(lg, m.b.team_id)}</div>
  </div>`;
}

function cardHead(iconName, title) {
  return `<div class="card-head"><h2><span class="icon-chip">${ICON_SVG[iconName]}</span>${title}</h2></div>`;
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

function matchupComparisonCard(leagueId) {
  const L = DIGEST.leagues[leagueId];
  const matchup = findMyMatchup(L);
  const card = el('div', 'card');
  if (!matchup) {
    card.innerHTML = cardHead('league', L.name) + '<p class="muted">No matchup this week (bye).</p>';
    return card;
  }
  const myDetail = L.teams_detail[String(L.my_team_id)];
  const oppDetail = L.teams_detail[String(matchup.opp.team_id)];
  const myStarters = (myDetail ? myDetail.roster : []).filter(p => p.is_starter);
  const oppStarters = (oppDetail ? oppDetail.roster : []).filter(p => p.is_starter);

  // Position-aligned rows: group each side's starters by lineup slot, then
  // pair them up slot-instance by slot-instance (e.g. RB1 vs RB1, RB2 vs
  // RB2) — same idea as ESPN's own side-by-side matchup view.
  const bySlot = (players) => players.reduce((acc, p) => { (acc[p.slot_id] = acc[p.slot_id] || []).push(p); return acc; }, {});
  const mySlots = bySlot(myStarters), oppSlots = bySlot(oppStarters);
  const allSlotIds = [...new Set([...Object.keys(mySlots), ...Object.keys(oppSlots)])]
    .sort((a, b) => a - b);

  let rows = '';
  allSlotIds.forEach(slotId => {
    const mine = mySlots[slotId] || [], theirs = oppSlots[slotId] || [];
    const count = Math.max(mine.length, theirs.length);
    for (let i = 0; i < count; i++) {
      const mp = mine[i], op = theirs[i];
      rows += `<div class="matchup-row">
        <div class="mp mp-mine">${mp ? `<span class="mp-name">${mp.name}</span><span class="mp-pts">${mp.points === null ? '—' : mp.points.toFixed(1)}</span>` : '<span class="muted">—</span>'}</div>
        <div class="mp-slot">${SLOT_LABELS[slotId] || slotId}</div>
        <div class="mp mp-theirs">${op ? `<span class="mp-pts">${op.points === null ? '—' : op.points.toFixed(1)}</span><span class="mp-name">${op.name}</span>` : '<span class="muted">—</span>'}</div>
      </div>`;
    }
  });

  card.innerHTML = `
    <div class="mc-league-label">${L.name}</div>
    <div class="matchup-card-head">
      <div class="mc-team">${logoImg(leagueId, matchup.mine.team_id, 26)}<span class="mc-name">${L.my_team_name}</span></div>
      <div class="mc-score">${matchup.mine.score.toFixed(1)}<span class="mc-dash">–</span>${matchup.opp.score.toFixed(1)}</div>
      <div class="mc-team right"><span class="mc-name">${matchup.opp.name}</span>${logoImg(leagueId, matchup.opp.team_id, 26)}</div>
    </div>
    ${matchup.live ? '<div class="mc-live-row"><span class="badge live">LIVE</span></div>' : ''}
    <div class="matchup-divider"></div>
    ${rows}
  `;
  return card;
}

function renderHome(root) {
  root.innerHTML = '';

  // Home shows both leagues, always, regardless of the league switcher
  // (owner's explicit call, 2026-09-14) — the switcher only affects the
  // other single-team-scoped tabs (My Team/League/Managers/Analytics).
  // Two sections, both side by side per league: your own matchup
  // (position-by-position vs. this week's opponent), then the full
  // league scoreboard below it.
  const leagueIds = Object.keys(DIGEST.leagues);

  const bothMatchups = el('div', 'grid grid-2');
  leagueIds.forEach(lid => bothMatchups.appendChild(matchupComparisonCard(lid)));
  root.appendChild(bothMatchups);

  const bothFixtures = el('div', 'grid grid-2');
  leagueIds.forEach(lid => {
    const L = DIGEST.leagues[lid];
    const card = el('div', 'card');
    card.innerHTML = cardHead('league', `${L.name} — Week ${L.this_week.week} matchups`);
    L.this_week.matchups.forEach(m => card.appendChild(el('div', null, matchRow(lid, m))));
    bothFixtures.appendChild(card);
  });
  root.appendChild(bothFixtures);
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
  starters.forEach(p => rosterCard.appendChild(el('div', 'roster-row', `<div class="name">${p.name}</div><div class="pts">${p.points === null ? '—' : p.points.toFixed(1)}</div>`)));
  if (bench.length) {
    rosterCard.appendChild(el('div', 'muted', 'Bench'));
    bench.forEach(p => rosterCard.appendChild(el('div', 'roster-row bench', `<div class="name">${p.name}</div><div class="pts">${p.points === null ? '—' : p.points.toFixed(1)}</div>`)));
  }
  container.appendChild(rosterCard);
}

function renderMyTeam(root) {
  const L = DIGEST.leagues[currentLeague];
  root.innerHTML = `<div class="card">${cardHead('myteam', L.my_team_name)}</div>`;
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
    ${L.standings.map((s,i) => `<tr class="${s.is_owner ? 'owner-row' : ''}"><td>${i+1}</td><td>${logoImg(currentLeague, s.team_id)}${s.team_name}</td><td>${s.wins}-${s.losses}-${s.ties}</td><td>${s.points_for.toFixed(1)}</td><td>${s.points_against.toFixed(1)}</td></tr>`).join('')}
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
    ${L.leaderboard.map(t => `<tr><td>${logoImg(currentLeague, t.team_id)}${t.team_name}</td><td>${fmtPct(t.lineup_efficiency)}</td><td>${t.bench_points.toFixed(1)}</td></tr>`).join('')}
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
"""


def build_html(digest: dict) -> str:
    league_buttons = "".join(
        f'<button data-lid="{lid}" class="{"active" if i == 0 else ""}" onclick="switchLeague(\'{lid}\')">{l["name"]}</button>'
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
  <div class="sidebar">
    <div class="brand">Fantasy Football<span class="brand-sub">{digest['season_year']} season · Week {list(digest['leagues'].values())[0]['current_week']}</span></div>
    {nav_items}
  </div>
  <main>
    <div class="topbar">
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
