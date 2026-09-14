"""Phase 7 — builds dashboard.html, a single self-contained file.

Data is baked in as a <script> tag at generation time (same reasoning as
the FPL project: a local file:// page can't fetch a sibling JSON file).
Fresh visual identity for this project, not a reskin of the FPL dashboard
(owner's explicit call, 2026-09-13).

Usage:
    python -m src.build_dashboard
"""

from __future__ import annotations

import json
import sys

from . import config

CSS = """
:root {
  --bg: #0c1116;
  --card: rgba(22,28,36,0.72);
  --card-2: rgba(30,38,48,0.78);
  --ink: #eef1f4;
  --ink-soft: #93a1ae;
  --border: rgba(255,255,255,0.08);
  --accent: #e8a33d;
  --accent-ink: #0c1116;
  --accent-soft: rgba(232,163,61,0.14);
  --turf: #3a7d5c;
  --turf-soft: rgba(58,125,92,0.16);
  --loss: #e0605a;
  --loss-soft: rgba(224,96,90,0.14);
  --shadow: 0 1px 0 rgba(255,255,255,0.05) inset, 0 16px 40px rgba(0,0,0,0.5);
}
* { box-sizing: border-box; }
body {
  margin: 0; min-height: 100vh; color: var(--ink);
  background:
    radial-gradient(1100px 550px at 10% -10%, rgba(58,125,92,0.16), transparent 55%),
    radial-gradient(900px 600px at 105% 5%, rgba(232,163,61,0.10), transparent 55%),
    var(--bg);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
}
header { padding: 16px 22px; border-bottom: 1px solid var(--border); display: flex; flex-wrap: wrap; gap: 14px; align-items: center; justify-content: space-between; }
.brand { font-weight: 800; font-size: 16px; letter-spacing: -0.01em; }
.brand-sub { color: var(--ink-soft); font-size: 12px; }
.league-switch { display: flex; gap: 6px; background: var(--card); border: 1px solid var(--border); border-radius: 999px; padding: 4px; }
.league-switch button { border: none; background: transparent; color: var(--ink-soft); padding: 7px 14px; border-radius: 999px; font-size: 12.5px; font-weight: 700; cursor: pointer; }
.league-switch button.active { background: var(--accent); color: var(--accent-ink); }
.tabs { display: flex; gap: 4px; padding: 0 22px; border-bottom: 1px solid var(--border); overflow-x: auto; }
.tab { padding: 12px 14px; color: var(--ink-soft); font-size: 13px; font-weight: 700; cursor: pointer; border-bottom: 2px solid transparent; white-space: nowrap; }
.tab.active { color: var(--accent); border-bottom-color: var(--accent); }
main { max-width: 1080px; margin: 0 auto; padding: 20px 22px 60px; display: flex; flex-direction: column; gap: 16px; }
.page { display: none; flex-direction: column; gap: 16px; }
.page.active { display: flex; }
.grid { display: grid; gap: 14px; }
.grid-2 { grid-template-columns: 1fr 1fr; }
@media (max-width: 720px) { .grid-2 { grid-template-columns: 1fr; } }
.card { background: var(--card); border: 1px solid var(--border); border-radius: 16px; padding: 18px 20px; box-shadow: var(--shadow); overflow-x: auto; }
.card h2 { margin: 0 0 12px; font-size: 14px; }
.card h3 { margin: 0 0 8px; font-size: 12px; color: var(--ink-soft); text-transform: uppercase; letter-spacing: 0.05em; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th, td { text-align: left; padding: 8px 8px; border-bottom: 1px solid var(--border); }
th { color: var(--ink-soft); font-weight: 700; font-size: 10.5px; text-transform: uppercase; letter-spacing: 0.04em; }
tr.owner-row td { background: var(--accent-soft); }
.muted { color: var(--ink-soft); font-size: 12px; }
.badge { display: inline-block; font-size: 9.5px; font-weight: 800; text-transform: uppercase; padding: 2px 7px; border-radius: 999px; }
.badge.live { background: var(--loss-soft); color: var(--loss); }
.badge.prov { background: var(--accent-soft); color: var(--accent); }
.stat-grid { display: grid; grid-template-columns: repeat(4,1fr); gap: 10px; }
@media (max-width: 720px) { .stat-grid { grid-template-columns: repeat(2,1fr); } }
.stat { background: var(--card-2); border: 1px solid var(--border); border-radius: 12px; padding: 12px 14px; }
.stat .value { font-size: 21px; font-weight: 800; }
.stat .label { color: var(--ink-soft); font-size: 11px; margin-top: 2px; }
.match-row { display: flex; align-items: center; gap: 10px; padding: 8px 0; border-bottom: 1px solid var(--border); font-size: 13px; }
.match-row:last-child { border-bottom: none; }
.match-row .side { flex: 1; font-weight: 700; }
.match-row .side.right { text-align: right; }
.match-row .score { min-width: 90px; text-align: center; font-weight: 800; font-variant-numeric: tabular-nums; }
.logo { width: 22px; height: 22px; border-radius: 50%; object-fit: cover; vertical-align: middle; margin-right: 6px; background: var(--card-2); }
.roster-row { display: flex; align-items: center; gap: 8px; padding: 6px 0; border-bottom: 1px solid var(--border); font-size: 12.5px; }
.roster-row:last-child { border-bottom: none; }
.roster-row.bench { opacity: 0.55; }
.roster-row .name { flex: 1; }
.roster-row .pts { font-weight: 800; font-variant-numeric: tabular-nums; }
select { background: var(--card-2); color: var(--ink); border: 1px solid var(--border); border-radius: 8px; padding: 7px 10px; font-size: 13px; }
.alert { padding: 8px 10px; border-radius: 8px; background: var(--card-2); border: 1px solid var(--border); font-size: 12px; margin-bottom: 6px; }
.footer { text-align: center; color: var(--ink-soft); font-size: 11px; padding: 20px; }
"""

JS = """
let currentLeague = Object.keys(DIGEST.leagues)[0];
let currentTab = 'home';

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
  renderCurrentTab();
}
function switchTab(tab) {
  currentTab = tab;
  document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.dataset.tab === tab));
  document.querySelectorAll('.page').forEach(p => p.classList.toggle('active', p.id === 'page-' + tab));
  renderCurrentTab();
}
function renderCurrentTab() {
  const root = document.getElementById('page-' + currentTab);
  if (!root) return;
  ({ home: renderHome, myteam: renderMyTeam, league: renderLeague, managers: renderManagers, analytics: renderAnalytics })[currentTab](root);
}

function matchRow(lg, m) {
  return `<div class="match-row">
    <div class="side">${logoImg(lg, m.a.team_id)}${m.a.name}</div>
    <div class="score">${m.a.score.toFixed(1)} - ${m.b.score.toFixed(1)} ${m.live ? '<span class="badge live">LIVE</span>' : ''}</div>
    <div class="side right">${m.b.name}${logoImg(lg, m.b.team_id)}</div>
  </div>`;
}

function renderHome(root) {
  const L = DIGEST.leagues[currentLeague];
  root.innerHTML = '';

  const grid = el('div', 'grid grid-2');
  const standingsCard = el('div', 'card');
  standingsCard.innerHTML = `<h2>Standings</h2><table><thead><tr><th>#</th><th>Team</th><th>W-L-T</th><th>PF</th></tr></thead><tbody>
    ${L.standings.map((s,i) => `<tr class="${s.is_owner ? 'owner-row' : ''}"><td>${i+1}</td><td>${logoImg(currentLeague, s.team_id)}${s.team_name}<div class="muted">${s.manager || ''}</div></td><td>${s.wins}-${s.losses}-${s.ties}</td><td>${s.points_for.toFixed(1)}</td></tr>`).join('')}
  </tbody></table>`;
  grid.appendChild(standingsCard);

  const fixturesCard = el('div', 'card');
  fixturesCard.innerHTML = `<h2>Week ${L.this_week.week} matchups</h2>`;
  L.this_week.matchups.forEach(m => fixturesCard.appendChild(el('div', null, matchRow(currentLeague, m))));
  grid.appendChild(fixturesCard);
  root.appendChild(grid);

  if (L.alerts.items.length) {
    const box = el('div', 'card');
    box.innerHTML = `<h2>Alerts</h2>` + L.alerts.items.map(a => `<div class="alert">[${a.severity}] ${a.description}</div>`).join('');
    if (L.alerts.total_unresolved > L.alerts.items.length) box.innerHTML += `<p class="muted">+${L.alerts.total_unresolved - L.alerts.items.length} more not shown.</p>`;
    root.appendChild(box);
  }
}

function renderTeamDetail(container, detail, leagueId) {
  container.innerHTML = '';
  if (!detail || !detail.season_stats) { container.appendChild(el('p', 'muted', 'No data yet.')); return; }
  const s = detail.season_stats, w = detail.week_stats;
  const statGrid = el('div', 'stat-grid');
  statGrid.innerHTML = `
    <div class="stat"><div class="value">${s.record.w}-${s.record.l}-${s.record.t}</div><div class="label">Record</div></div>
    <div class="stat"><div class="value">${s.points_for.toFixed(1)}</div><div class="label">Points for</div></div>
    <div class="stat"><div class="value">${fmtPct(s.lineup_efficiency)}</div><div class="label">Lineup efficiency ${s.is_provisional ? '<span class="badge prov">early</span>' : ''}</div></div>
    <div class="stat"><div class="value">${s.total_bench_points.toFixed(1)}</div><div class="label">Bench points</div></div>
  `;
  container.appendChild(statGrid);

  if (w) {
    const wCard = el('div', 'card');
    wCard.innerHTML = `<h3>This week</h3><p class="muted">Actual ${w.actual_points.toFixed(1)} / optimal ${w.optimal_points.toFixed(1)} (${fmtPct(w.efficiency)}) — rank ${w.rank} of ${DIGEST.leagues[leagueId].teams.length}</p>`;
    container.appendChild(wCard);
  }

  const rosterCard = el('div', 'card');
  rosterCard.appendChild(el('h3', null, 'Roster'));
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
  root.innerHTML = `<div class="card"><h2>${L.my_team_name}</h2></div>`;
  const wrap = el('div');
  renderTeamDetail(wrap, L.my_team_detail, currentLeague);
  root.appendChild(wrap);

  if (L.waiver_moves.length) {
    const wCard = el('div', 'card');
    wCard.innerHTML = `<h2>Waiver moves</h2><table><thead><tr><th>Week</th><th>Added</th><th>Dropped</th><th>Net (${L.waiver_moves[0].horizon_weeks}wk)</th></tr></thead><tbody>
      ${L.waiver_moves.map(m => `<tr><td>${m.week}</td><td>${m.added}</td><td>${m.dropped || '—'}</td><td>${m.is_complete ? (m.net === null ? '—' : m.net.toFixed(1)) : 'incomplete'}</td></tr>`).join('')}
    </tbody></table>`;
    root.appendChild(wCard);
  }
}

function renderLeague(root) {
  const L = DIGEST.leagues[currentLeague];
  root.innerHTML = `<div class="card"><h2>Standings — after Week ${L.this_week.week}</h2><table><thead><tr><th>#</th><th>Team</th><th>W-L-T</th><th>PF</th><th>PA</th></tr></thead><tbody>
    ${L.standings.map((s,i) => `<tr class="${s.is_owner ? 'owner-row' : ''}"><td>${i+1}</td><td>${logoImg(currentLeague, s.team_id)}${s.team_name}</td><td>${s.wins}-${s.losses}-${s.ties}</td><td>${s.points_for.toFixed(1)}</td><td>${s.points_against.toFixed(1)}</td></tr>`).join('')}
  </tbody></table></div>`;
  const mCard = el('div', 'card');
  mCard.innerHTML = `<h2>Week ${L.this_week.week} matchups</h2>`;
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
  selectCard.appendChild(el('h2', null, 'Managers'));
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
  root.innerHTML = `<div class="card"><h2>Lineup efficiency leaderboard</h2><table><thead><tr><th>Team</th><th>Efficiency</th><th>Bench pts</th></tr></thead><tbody>
    ${L.leaderboard.map(t => `<tr>${t.is_provisional ? '' : ''}<td>${logoImg(currentLeague, t.team_id)}${t.team_name}</td><td>${fmtPct(t.lineup_efficiency)}</td><td>${t.bench_points.toFixed(1)}</td></tr>`).join('')}
  </tbody></table>
  <p class="muted">Luck index, power rankings, and playoff odds unlock at 5 and 7 weeks played (owner-confirmed gates) — insufficient sample right now.</p>
  </div>`;
}

document.addEventListener('DOMContentLoaded', () => {
  renderCurrentTab();
});
"""


def build_html(digest: dict) -> str:
    league_buttons = "".join(
        f'<button data-lid="{lid}" class="{"active" if i == 0 else ""}" onclick="switchLeague(\'{lid}\')">{l["name"]}</button>'
        for i, (lid, l) in enumerate(digest["leagues"].items())
    )
    tabs = [("home", "Home"), ("myteam", "My Team"), ("league", "League"), ("managers", "Managers"), ("analytics", "Analytics")]
    tab_buttons = "".join(
        f'<div class="tab {"active" if i == 0 else ""}" data-tab="{t}" onclick="switchTab(\'{t}\')">{label}</div>'
        for i, (t, label) in enumerate(tabs)
    )
    pages = "".join(f'<div class="page {"active" if i == 0 else ""}" id="page-{t}"></div>' for i, (t, _) in enumerate(tabs))

    digest_json = json.dumps(digest)

    return f"""<meta charset="utf-8">
<title>Fantasy Football — Multi-League Dashboard</title>
<style>{CSS}</style>
<header>
  <div>
    <div class="brand">Fantasy Football Intelligence</div>
    <div class="brand-sub">Week {list(digest['leagues'].values())[0]['current_week']} · {digest['season_year']} season</div>
  </div>
  <div class="league-switch">{league_buttons}</div>
</header>
<div class="tabs">{tab_buttons}</div>
<main>{pages}</main>
<div class="footer">Generated {digest['generated_at']} · Fact = stored raw data. Computed = derived by a documented formula. See CLAUDE.md.</div>
<script>const DIGEST = {digest_json};</script>
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
