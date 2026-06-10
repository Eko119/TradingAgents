/* TradingAgents Console — hash-routed single-page app, no dependencies.
   All dynamic text is escaped before any markdown transform runs; report
   content is LLM/news-derived and must be treated as untrusted. */
"use strict";

const $view = document.getElementById("view");
const $conn = document.getElementById("conn-status");
let pollTimer = null;

/* ---------- utilities ---------- */

const esc = (s) => String(s ?? "")
  .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
  .replace(/"/g, "&quot;").replace(/'/g, "&#39;");

async function api(path, opts) {
  const res = await fetch(path, opts);
  let body = null;
  try { body = await res.json(); } catch { /* non-JSON error body */ }
  if (!res.ok) {
    const msg = body && body.error ? body.error : `${res.status} ${res.statusText}`;
    const err = new Error(msg); err.status = res.status; throw err;
  }
  return body;
}

function setConn(ok) {
  $conn.className = "conn " + (ok ? "ok" : "bad");
  $conn.textContent = ok ? "connected" : "server unreachable";
}

/* Minimal markdown renderer (headings, emphasis, code, lists, tables,
   quotes, hr, http(s) links). Input is escaped first, so the only HTML
   in the output is what this function emits. */
function renderMarkdown(md) {
  const lines = esc(md).replace(/\r\n/g, "\n").split("\n");
  const out = [];
  let inCode = false, listStack = null, tableRows = null, para = [];

  const inline = (s) => s
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/__([^_]+)__/g, "<strong>$1</strong>")
    .replace(/\*([^*\s][^*]*)\*/g, "<em>$1</em>")
    .replace(/\[([^\]]+)\]\((https?:[^)\s]+)\)/g,
      '<a href="$2" rel="noopener noreferrer" target="_blank">$1</a>');

  const flushPara = () => { if (para.length) { out.push(`<p>${inline(para.join(" "))}</p>`); para = []; } };
  const flushList = () => { if (listStack) { out.push(`</${listStack}>`); listStack = null; } };
  const flushTable = () => {
    if (!tableRows) return;
    const [head, ...rows] = tableRows;
    const cells = (r, tag) => r.split("|").slice(1, -1).map(c => `<${tag}>${inline(c.trim())}</${tag}>`).join("");
    out.push("<table><thead><tr>" + cells(head, "th") + "</tr></thead><tbody>");
    for (const r of rows) out.push("<tr>" + cells(r, "td") + "</tr>");
    out.push("</tbody></table>");
    tableRows = null;
  };

  for (const raw of lines) {
    const line = raw;
    if (line.trim().startsWith("```")) {
      flushPara(); flushList(); flushTable();
      out.push(inCode ? "</code></pre>" : "<pre><code>");
      inCode = !inCode; continue;
    }
    if (inCode) { out.push(line); continue; }

    if (/^\s*\|.*\|\s*$/.test(line)) {
      flushPara(); flushList();
      if (/^\s*\|[\s:|-]+\|\s*$/.test(line)) continue;       // separator row
      (tableRows = tableRows || []).push(line.trim());
      continue;
    }
    flushTable();

    const h = line.match(/^(#{1,4})\s+(.*)$/);
    if (h) { flushPara(); flushList(); out.push(`<h${h[1].length}>${inline(h[2])}</h${h[1].length}>`); continue; }
    if (/^\s*([-*_])\s*\1\s*\1[\s\1]*$/.test(line)) { flushPara(); flushList(); out.push("<hr>"); continue; }

    const li = line.match(/^\s*(?:[-*+]|(\d+)\.)\s+(.*)$/);
    if (li) {
      flushPara();
      const want = li[1] ? "ol" : "ul";
      if (listStack !== want) { flushList(); out.push(`<${want}>`); listStack = want; }
      out.push(`<li>${inline(li[2])}</li>`); continue;
    }
    flushList();

    const q = line.match(/^\s*&gt;\s?(.*)$/);
    if (q) { flushPara(); out.push(`<blockquote><p>${inline(q[1])}</p></blockquote>`); continue; }

    if (!line.trim()) { flushPara(); continue; }
    para.push(line.trim());
  }
  flushPara(); flushList(); flushTable();
  if (inCode) out.push("</code></pre>");
  return out.join("\n");
}

const decisionBadge = (d) => {
  if (!d) return "";
  const up = String(d).toUpperCase();
  const cls = up.includes("BUY") ? "buy" : up.includes("SELL") ? "sell" : "hold";
  return `<span class="badge badge-${cls}">${esc(up.slice(0, 28))}</span>`;
};
const statusBadge = (s) => s ? `<span class="badge badge-${esc(s)}">${esc(s)}</span>` : "";
const sectionTitle = (k) => k.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());

const loading = (what) => `<div class="loading"><span class="spinner" aria-hidden="true"></span>Loading ${what}…</div>`;
const errorBanner = (msg, retryHash) =>
  `<div class="banner banner-error" role="alert">${esc(msg)}
   ${retryHash ? `<button class="btn-link" onclick="location.hash='${retryHash}';route()">Retry</button>` : ""}</div>`;

/* ---------- views ---------- */

async function viewDashboard() {
  $view.innerHTML = `<h2>Dashboard</h2>` + loading("runs and results");
  let runs, results;
  try {
    [runs, results] = await Promise.all([api("/api/runs"), api("/api/results")]);
  } catch (e) { $view.innerHTML = `<h2>Dashboard</h2>` + errorBanner(e.message, "/dashboard"); return; }

  const active = runs.runs.filter(r => r.status === "running" || r.status === "starting");
  const recent = results.results.slice(0, 8);

  $view.innerHTML = `
    <h2>Dashboard</h2>
    <p class="lede">Live runs from this console session and your most recent persisted analyses.</p>
    <div class="card">
      <h3>Active runs</h3>
      ${active.length ? runTable(runs.runs) : `<div class="empty">No analysis is running. Start one from <a href="#/new">New Analysis</a>.</div>`}
    </div>
    <div class="card">
      <h3>Recent results</h3>
      ${recent.length ? resultTable(recent) : `<div class="empty">No persisted analyses yet — results land here after your first run (CLI or console).</div>`}
    </div>`;

  if (active.length) schedulePoll(viewDashboard);
}

function runTable(runs) {
  const rows = runs.map(r => `
    <tr>
      <td class="mono">${esc(r.ticker)}</td>
      <td class="mono">${esc(r.date)}</td>
      <td>${statusBadge(r.status)}</td>
      <td>${r.decision ? decisionBadge(r.decision) : (r.error ? esc(r.error.slice(0, 80)) : "—")}</td>
      <td class="opt mono">${esc(r.started_at || "")}</td>
      <td><a href="#/runs/${esc(r.id)}">details</a></td>
    </tr>`).join("");
  return `<table class="list"><thead><tr>
    <th>Ticker</th><th>Date</th><th>Status</th><th>Outcome</th><th class="opt">Started (UTC)</th><th></th>
  </tr></thead><tbody>${rows}</tbody></table>`;
}

function resultTable(results) {
  const rows = results.map(r => `
    <tr>
      <td class="mono">${esc(r.ticker)}</td>
      <td class="mono">${esc(r.date)}</td>
      <td>${r.decision ? decisionBadge(r.decision) : (r.status ? statusBadge(r.status) : "")}</td>
      <td class="opt">${r.sections.length} section${r.sections.length === 1 ? "" : "s"}</td>
      <td><a href="#/results/${esc(r.ticker)}/${esc(r.date)}">open</a></td>
    </tr>`).join("");
  return `<table class="list"><thead><tr>
    <th>Ticker</th><th>Date</th><th>Decision</th><th class="opt">Reports</th><th></th>
  </tr></thead><tbody>${rows}</tbody></table>`;
}

async function viewResults() {
  $view.innerHTML = `<h2>Results</h2>` + loading("analyses");
  let data;
  try { data = await api("/api/results"); }
  catch (e) { $view.innerHTML = `<h2>Results</h2>` + errorBanner(e.message, "/results"); return; }
  $view.innerHTML = `
    <h2>Results</h2>
    <p class="lede">Every persisted analysis found in the results directory.</p>
    ${data.results.length ? `<div class="card">${resultTable(data.results)}</div>`
      : `<div class="empty">Nothing here yet. Run an analysis from <a href="#/new">New Analysis</a> or the CLI (<code>tradingagents</code>).</div>`}`;
}

async function viewResultDetail(ticker, date) {
  const title = `${esc(ticker)} · ${esc(date)}`;
  $view.innerHTML = `<h2>${title}</h2>` + loading("report");
  let d;
  try { d = await api(`/api/results/${encodeURIComponent(ticker)}/${encodeURIComponent(date)}`); }
  catch (e) { $view.innerHTML = `<h2>${title}</h2>` + errorBanner(e.message, `/results`); return; }

  const sections = Object.entries(d.sections).map(([name, body], i) => `
    <details class="section" ${name === "final_trade_decision" || i === 0 ? "open" : ""}>
      <summary>${esc(sectionTitle(name))}</summary>
      <div class="section-body report">${renderMarkdown(body)}</div>
    </details>`).join("");

  $view.innerHTML = `
    <div class="toolbar">
      <h2 style="margin:0">${title}</h2>
      ${d.status && d.status.decision ? decisionBadge(d.status.decision) : ""}
      ${d.status && d.status.status ? statusBadge(d.status.status) : ""}
      <span class="spacer"></span>
      <a class="btn" href="/api/results/${encodeURIComponent(ticker)}/${encodeURIComponent(date)}/export" download>Export markdown</a>
    </div>
    ${d.status && d.status.error ? errorBanner("Run failed: " + d.status.error) : ""}
    ${sections || `<div class="empty">No report sections were persisted for this run.</div>`}
    ${d.log_tail ? `<h3>Message log (tail)</h3><div class="log-well" tabindex="0">${esc(d.log_tail)}</div>` : ""}`;
}

async function viewRunDetail(id) {
  $view.innerHTML = `<h2>Run</h2>` + loading("run status");
  let r;
  try { r = await api(`/api/runs/${encodeURIComponent(id)}`); }
  catch (e) { $view.innerHTML = `<h2>Run</h2>` + errorBanner(e.message, "/dashboard"); return; }

  const finished = r.status === "completed" || r.status === "failed";
  $view.innerHTML = `
    <div class="toolbar">
      <h2 style="margin:0">${esc(r.ticker)} · ${esc(r.date)}</h2>
      ${statusBadge(r.status)} ${r.decision ? decisionBadge(r.decision) : ""}
    </div>
    ${r.error ? errorBanner(r.error) : ""}
    ${r.status === "completed" ? `<div class="banner banner-ok">Analysis complete — <a href="#/results/${esc(r.ticker)}/${esc(r.date)}">open the report</a>.</div>` : ""}
    <div class="card"><dl class="kv">
      <dt>Run ID</dt><dd>${esc(r.id)}</dd>
      <dt>Asset type</dt><dd>${esc(r.asset_type)}</dd>
      <dt>Started</dt><dd>${esc(r.started_at || "—")}</dd>
      <dt>Finished</dt><dd>${esc(r.finished_at || "—")}</dd>
    </dl></div>
    <h3>Runner output (tail)</h3>
    <div class="log-well" tabindex="0">${esc(r.log_tail || "(no output yet)")}</div>`;

  if (!finished) schedulePoll(() => viewRunDetail(id));
}

function viewNew() {
  const today = new Date().toISOString().slice(0, 10);
  $view.innerHTML = `
    <h2>New Analysis</h2>
    <p class="lede">Runs the full multi-agent pipeline in a background process using your configured provider. LLM API calls cost money and take several minutes.</p>
    <div id="form-feedback"></div>
    <form id="run-form" class="card" novalidate>
      <div class="field">
        <label for="f-ticker">Ticker</label>
        <input id="f-ticker" name="ticker" required autocomplete="off" spellcheck="false"
               placeholder="NVDA" pattern="[A-Za-z0-9._\\-^=+]{1,32}">
        <p class="hint">Stocks (NVDA), indices (^GSPC), futures (GC=F), crypto (BTC-USD)…</p>
      </div>
      <div class="field">
        <label for="f-date">Analysis date</label>
        <input id="f-date" name="date" type="date" required value="${today}" max="${today}">
        <p class="hint">Historical dates analyze that day's data snapshot.</p>
      </div>
      <div class="field">
        <label for="f-asset">Asset type</label>
        <select id="f-asset" name="asset_type">
          <option value="stock" selected>Stock / index / forex</option>
          <option value="crypto">Crypto (analysis-only mode)</option>
        </select>
      </div>
      <button class="btn btn-primary" type="submit">Start analysis</button>
    </form>`;

  document.getElementById("run-form").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const fb = document.getElementById("form-feedback");
    const btn = ev.target.querySelector("button[type=submit]");
    const payload = {
      ticker: document.getElementById("f-ticker").value,
      date: document.getElementById("f-date").value,
      asset_type: document.getElementById("f-asset").value,
    };
    btn.disabled = true; btn.textContent = "Starting…";
    try {
      const run = await api("/api/runs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      location.hash = `#/runs/${run.id}`;
    } catch (e) {
      fb.innerHTML = errorBanner(e.message);
      btn.disabled = false; btn.textContent = "Start analysis";
      fb.querySelector(".banner") && fb.querySelector(".banner").focus && fb.querySelector(".banner").focus();
    }
  });
}

async function viewMemory() {
  $view.innerHTML = `<h2>Decision Log</h2>` + loading("decision log");
  let d;
  try { d = await api("/api/memory"); }
  catch (e) { $view.innerHTML = `<h2>Decision Log</h2>` + errorBanner(e.message, "/memory"); return; }
  $view.innerHTML = `
    <h2>Decision Log</h2>
    <p class="lede">The persistent memory the Portfolio Manager consults — past decisions, realized returns, lessons.</p>
    ${d.markdown ? `<div class="card report">${renderMarkdown(d.markdown)}</div>`
      : `<div class="empty">No decision log yet. It is created automatically after the first completed analysis.</div>`}`;
}

async function viewSettings() {
  $view.innerHTML = `<h2>Settings</h2>` + loading("configuration");
  let d;
  try { d = await api("/api/config"); }
  catch (e) { $view.innerHTML = `<h2>Settings</h2>` + errorBanner(e.message, "/settings"); return; }

  const cfgRows = Object.entries(d.config).map(([k, v]) =>
    `<dt>${esc(k)}</dt><dd>${esc(v === null ? "(default)" : typeof v === "object" ? JSON.stringify(v) : v)}</dd>`).join("");
  const provRows = Object.entries(d.providers).map(([name, p]) => `
    <tr>
      <td class="mono">${esc(name)}</td>
      <td class="mono">${esc(p.env_var || "— (no key needed)")}</td>
      <td>${p.key_set === null ? "" : p.key_set
        ? '<span class="badge badge-completed">set</span>'
        : '<span class="badge badge-failed">missing</span>'}</td>
    </tr>`).join("");

  $view.innerHTML = `
    <h2>Settings</h2>
    <p class="lede">Read-only view of the effective configuration (version ${esc(d.version)}). Change values via <code>.env</code> / <code>TRADINGAGENTS_*</code> env vars and restart the console.</p>
    <div class="card"><h3>Effective configuration</h3><dl class="kv">${cfgRows}</dl></div>
    <div class="card"><h3>Provider API keys</h3>
      <p class="hint" style="color:var(--text-dim)">Only presence is shown — key values never leave the server process.</p>
      <table class="list"><thead><tr><th>Provider</th><th>Env var</th><th>Status</th></tr></thead><tbody>${provRows}</tbody></table>
    </div>`;
}

/* ---------- router ---------- */

const routes = [
  [/^\/?$/,                        () => viewDashboard()],
  [/^\/dashboard$/,                () => viewDashboard()],
  [/^\/results$/,                  () => viewResults()],
  [/^\/results\/([^/]+)\/([^/]+)$/, (m) => viewResultDetail(decodeURIComponent(m[1]), decodeURIComponent(m[2]))],
  [/^\/new$/,                      () => viewNew()],
  [/^\/runs\/([^/]+)$/,            (m) => viewRunDetail(decodeURIComponent(m[1]))],
  [/^\/memory$/,                   () => viewMemory()],
  [/^\/settings$/,                 () => viewSettings()],
];

function schedulePoll(fn) {
  clearTimeout(pollTimer);
  pollTimer = setTimeout(fn, 2500);
}

function route() {
  clearTimeout(pollTimer);
  const hash = location.hash.replace(/^#/, "") || "/dashboard";
  for (const a of document.querySelectorAll(".nav a")) {
    const current = hash.startsWith("/" + a.dataset.nav) ||
      (a.dataset.nav === "dashboard" && (hash === "/" || hash === "")) ||
      (a.dataset.nav === "results" && hash.startsWith("/results")) ||
      (a.dataset.nav === "dashboard" && hash.startsWith("/runs"));
    if (current) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
  }
  for (const [re, handler] of routes) {
    const m = hash.match(re);
    if (m) { handler(m); return; }
  }
  $view.innerHTML = errorBanner(`Unknown page: ${hash}`) + `<p><a href="#/dashboard">Back to dashboard</a></p>`;
}

async function heartbeat() {
  try { await api("/api/health"); setConn(true); }
  catch { setConn(false); }
  setTimeout(heartbeat, 15000);
}

window.addEventListener("hashchange", route);
route();
heartbeat();
