"""Self-contained HTML report: real data, working filters, no external assets."""

from __future__ import annotations

import json

from .. import __version__
from ..evidence import Investigation

TEMPLATE = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__ — ProtectREVERSE</title>
<style>
:root{--bg:#f7f7f5;--fg:#16181d;--muted:#5d6470;--line:#d9dce1;--card:#fff;
--obs:#0f6b3d;--inf:#8a5a00;--unk:#5d6470;--nc:#7a3b8f;--bad:#a11f2b;--accent:#1f4b8f}
@media (prefers-color-scheme:dark){:root{--bg:#111317;--fg:#e8eaee;--muted:#9aa2af;--line:#2a2f38;
--card:#171a20;--obs:#57c48b;--inf:#e0aa55;--unk:#9aa2af;--nc:#c08ad8;--bad:#ef7a86;--accent:#7aa7ea}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
header{padding:28px 24px 16px;border-bottom:1px solid var(--line)}
h1{margin:0 0 6px;font-size:22px;letter-spacing:-.01em}
.meta{color:var(--muted);font-size:13px}
main{max-width:1080px;margin:0 auto;padding:20px 24px 64px}
nav{display:flex;gap:6px;flex-wrap:wrap;margin:16px 0 22px}
nav button,.chip{background:var(--card);border:1px solid var(--line);color:var(--fg);padding:7px 12px;
border-radius:999px;font-size:13px;cursor:pointer}
nav button[aria-selected="true"]{border-color:var(--accent);color:var(--accent);font-weight:600}
.grid{display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(150px,1fr))}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px}
.card .n{font-size:22px;font-weight:600}
.card .l{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.06em}
section[hidden]{display:none}
article.finding{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px;margin:10px 0}
.claim{margin:6px 0 8px;font-weight:500}
.tag{font-size:11px;letter-spacing:.04em;text-transform:uppercase;border-radius:999px;padding:2px 8px;
border:1px solid currentColor;margin-right:6px}
.s-OBSERVED{color:var(--obs)}.s-INFERRED{color:var(--inf)}.s-UNKNOWN{color:var(--unk)}
.s-NOT_CHECKED{color:var(--nc)}.s-CONTRADICTED{color:var(--bad)}
.ev{font:12px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--muted);
border-left:2px solid var(--line);padding-left:10px;margin:6px 0}
ul{margin:6px 0 0 18px;padding:0}
li{margin:2px 0}
input[type=search]{width:100%;max-width:340px;padding:8px 10px;border-radius:8px;
border:1px solid var(--line);background:var(--card);color:var(--fg)}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{text-align:left;padding:7px 8px;border-bottom:1px solid var(--line)}
code{font-size:12px;background:rgba(127,127,127,.14);padding:1px 5px;border-radius:4px}
footer{color:var(--muted);font-size:12px;border-top:1px solid var(--line);margin-top:28px;padding-top:14px}
</style></head><body>
<header>
<h1>__TITLE__</h1>
<div class="meta">ProtectREVERSE __VERSION__ · investigation <code>__ID__</code> · __KIND__ · generated __WHEN__</div>
</header>
<main>
<nav role="tablist">
<button role="tab" aria-selected="true" data-tab="overview">Overview</button>
<button role="tab" aria-selected="false" data-tab="findings">Findings</button>
<button role="tab" aria-selected="false" data-tab="evidence">Evidence index</button>
<button role="tab" aria-selected="false" data-tab="api">API surface</button>
<button role="tab" aria-selected="false" data-tab="graph">Module graph</button>
<button role="tab" aria-selected="false" data-tab="limits">Scope &amp; limits</button>
</nav>

<div id="tab-overview">
<div class="grid" id="cards"></div>
<h3 style="margin-top:22px">What was established</h3>
<div id="highlights"></div>
</div>

<div id="tab-findings" hidden>
<p><input type="search" id="q" placeholder="Filter findings by text…" aria-label="Filter findings"></p>
<p id="filters"></p>
<div id="findings"></div>
</div>

<div id="tab-evidence" hidden><div id="evidence"></div></div>
<div id="tab-api" hidden><div id="api"></div></div>
<div id="tab-graph" hidden><div id="graph"></div></div>
<div id="tab-limits" hidden><div id="limits"></div></div>

<footer>Static analysis is not proof of runtime behaviour. Findings carry status and confidence;
absence of a finding is not evidence of absence. Provided AS IS — see LICENSE-EULA.md.</footer>
</main>
<script id="data" type="application/json">__DATA__</script>
<script>
const inv = JSON.parse(document.getElementById('data').textContent);
const F = inv.findings;
const esc = (s) => String(s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));

// tabs
document.querySelectorAll('nav button').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('nav button').forEach(b => b.setAttribute('aria-selected', String(b === btn)));
    ['overview','findings','evidence','api','graph','limits'].forEach(t => {
      document.getElementById('tab-' + t).hidden = t !== btn.dataset.tab;
    });
  });
});

// cards
const counts = inv.counts.by_status;
document.getElementById('cards').innerHTML = [
  ['Findings', inv.counts.findings],
  ['Observed', counts.OBSERVED || 0],
  ['Inferred', counts.INFERRED || 0],
  ['Unknown', counts.UNKNOWN || 0],
  ['Not checked', counts.NOT_CHECKED || 0],
  ['Sources', inv.sources.length],
].map(([l, n]) => `<div class="card"><div class="n">${n}</div><div class="l">${l}</div></div>`).join('');

// highlights = observed findings first
const order = ['OBSERVED','INFERRED','UNKNOWN','CONTRADICTED','NOT_CHECKED'];
const sorted = [...F].sort((a,b) => order.indexOf(a.status) - order.indexOf(b.status));
document.getElementById('highlights').innerHTML = sorted.slice(0, 6).map(f => `
  <article class="finding">
    <span class="tag s-${f.status}">${f.status.replace('_',' ')}</span>
    <span class="tag s-${f.status}">${f.confidence}</span>
    <div class="claim">${esc(f.claim)}</div>
    <div class="ev">${esc(f.category)} · ${esc(f.id)}</div>
  </article>`).join('');

// finding renderer
function renderFinding(f) {
  const ev = f.evidence.map(e => `<div class="ev">${esc(e.source)} ${esc(e.locator)}<br>${esc(e.excerpt || '')}</div>`).join('');
  const lim = f.limitations.length ? `<ul>${f.limitations.map(l => `<li>${esc(l)}</li>`).join('')}</ul>` : '';
  return `<article class="finding">
    <span class="tag s-${f.status}">${f.status.replace('_',' ')}</span>
    <span class="tag s-${f.status}">${f.confidence}</span>
    <span class="tag s-${f.status}">${esc(f.id)}</span>
    <div class="claim">${esc(f.claim)}</div>
    ${ev}${lim}
  </article>`;
}
const statuses = [...new Set(F.map(f => f.status))];
let active = 'ALL';
function drawFilters() {
  document.getElementById('filters').innerHTML = ['ALL', ...statuses].map(s =>
    `<button class="chip" data-status="${s}" aria-pressed="${s === active}">${s.replace('_',' ')}</button>`).join(' ');
  document.querySelectorAll('.chip').forEach(c => c.addEventListener('click', () => {
    active = c.dataset.status; drawFilters(); drawFindings();
  }));
}
function drawFindings() {
  const q = document.getElementById('q').value.toLowerCase();
  const rows = F.filter(f => (active === 'ALL' || f.status === active) &&
    (!q || (f.claim + ' ' + f.category + ' ' + f.id).toLowerCase().includes(q)));
  document.getElementById('findings').innerHTML = rows.length ? rows.map(renderFinding).join('')
    : '<p class="meta">No findings match this filter.</p>';
}
document.getElementById('q').addEventListener('input', drawFindings);
drawFilters(); drawFindings();

// evidence index
const evRows = F.flatMap(f => f.evidence.map(e => ({ id: f.id, claim: f.claim, ...e })));
document.getElementById('evidence').innerHTML = evRows.length ? `<table><thead><tr>
  <th>Finding</th><th>Source</th><th>Locator</th><th>Collected</th></tr></thead><tbody>${
  evRows.map(e => `<tr><td>${esc(e.id)}</td><td>${esc(e.source)}</td><td>${esc(e.locator)}</td>
  <td>${esc(e.collected_at)}</td></tr>`).join('')}</tbody></table>` : '<p class="meta">No evidence rows recorded.</p>';

// api surface
const apiFinding = F.find(t => t.category === 'api.routes');
const endpoints = apiFinding && apiFinding.details.endpoints ? apiFinding.details.endpoints : [];
document.getElementById('api').innerHTML = endpoints.length ? `<table><thead><tr>
  <th>Method</th><th>Path</th><th>Framework</th><th>File</th><th>Line</th></tr></thead><tbody>${
  endpoints.map(e => `<tr><td>${esc(e.method)}</td><td><code>${esc(e.path)}</code></td>
  <td>${esc(e.framework)}</td><td>${esc(e.file)}</td><td>${e.line}</td></tr>`).join('')}</tbody></table>`
  : '<p class="meta">No route declarations were detected in this release.</p>';

// module graph (textual fallback, real edges)
const graphFinding = F.find(t => t.category === 'architecture.imports');
const edges = graphFinding && graphFinding.details.edges ? graphFinding.details.edges : {};
const graphRows = Object.entries(edges).flatMap(([src, targets]) => targets.map(t => `<tr><td><code>${esc(src)}</code></td><td><code>${esc(t)}</code></td></tr>`));
document.getElementById('graph').innerHTML = graphRows.length ? `<table><thead><tr>
  <th>Module</th><th>Imports</th></tr></thead><tbody>${graphRows.join('')}</tbody></table>`
  : '<p class="meta">No internal import edges were resolved.</p>';

// limits
const scope = F.find(t => t.category === 'scope.not_checked');
document.getElementById('limits').innerHTML = `
  <p class="meta">Method: ${esc(__METHOD__)}</p>
  <ul>${(scope ? scope.limitations : []).map(l => `<li>${esc(l)}</li>`).join('')}</ul>
  ${inv.warnings.length ? `<h3>Warnings</h3><ul>${inv.warnings.map(w => `<li>${esc(w)}</li>`).join('')}</ul>` : ''}`;
</script>
</body></html>
"""


def render_html(inv: Investigation) -> str:
    method = {
        "directory": "local directory import, read-only",
        "archive": "bounded, traversal-safe ZIP extraction",
        "repository": "shallow HTTPS clone with pinned revision",
    }.get(inv.target_kind, "unknown")

    html = TEMPLATE
    html = html.replace("__TITLE__", inv.target.replace("<", "&lt;"))
    html = html.replace("__VERSION__", __version__)
    html = html.replace("__ID__", inv.id)
    html = html.replace("__KIND__", inv.target_kind)
    html = html.replace("__WHEN__", inv.created_at)
    html = html.replace("__METHOD__", json.dumps(method))
    html = html.replace("__DATA__", json.dumps(inv.to_dict(), ensure_ascii=False).replace("</", "<\\/"))
    return html
