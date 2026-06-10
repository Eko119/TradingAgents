# GUI Feasibility Analysis — TradingAgents

> Phase B of the verification audit, 2026-06-10. Question: would the repository materially benefit from a graphical interface, and if so, what kind?

## Current UX limitations (CLI-only)

| Dimension | Assessment |
|---|---|
| Onboarding | Good for the *run* path (interactive wizard), poor for the *understand* path — a new user must read the README to learn where anything lives. |
| Learnability | The wizard teaches the workflow well, but options live behind sequential prompts; there is no overview of what is configurable. |
| Discoverability | **Weak.** Completed analyses are markdown files under `~/.tradingagents/logs/<TICKER>/<DATE>/reports/`; nothing in the product surfaces them after the run ends. The decision log (`trading_memory.md`) is similarly invisible. |
| Workflow efficiency | Re-running with the same settings requires re-answering every prompt (env-var skip exists but is expert-level). Comparing two past runs requires a file manager and a markdown viewer. |
| Error recovery | Good during a run (checkpoint resume); poor before it — provider/key/config problems surface one prompt at a time. |
| Progress visibility | **Excellent live** (rich panels) but only while the terminal is attached; close it and visibility is gone. |
| Configuration management | Spread across `.env`, `TRADINGAGENTS_*` env vars, and prompt answers; no single read-out of "what will this run use". |
| Data visualization / reporting | Reports are well-structured markdown, but never rendered — users read raw markup or pipe files elsewhere. |
| Operational monitoring | None outside the live TUI. |

## Would a GUI materially help?

**Yes — for inspection, configuration transparency, and run management.** The framework already persists everything needed (report sections, message logs, decision log, config); what's missing is a surface that shows it. **No — for replacing the CLI**: the wizard remains the best fit for guided first runs and remote/SSH use, and the rich live view is genuinely good. The GUI should complement, not replace.

## Options considered

| Approach | Effort | New deps | Verdict |
|---|---|---|---|
| Streamlit/Gradio dashboard | Low | Heavy (50+ transitive packages, pins conflict risk with langchain stack) | Rejected — dependency governance; fights the existing `uv.lock` discipline. |
| FastAPI + React SPA | High | fastapi, uvicorn, node toolchain, build step | Rejected — build pipeline and JS toolchain for a single-user local console is disproportionate. |
| **Stdlib `http.server` + single-page vanilla frontend** | Medium | **Zero** | **Selected.** Deterministic (no build step, no CDN), maintainable (one Python module + three static files), consistent with the repo's zero-magic architecture. |
| Textual TUI upgrade | Medium | textual | Rejected — doesn't solve discoverability/rendering; still terminal-bound. |

## Selected approach: local Web Console

A localhost-only web console (`tradingagents-web`, `make web`) providing:

1. **Dashboard** — active runs with live status, recent results at a glance.
2. **Results browser** — every persisted analysis, rendered report sections, message log tail, markdown export.
3. **New Analysis** — form-driven run launch (ticker, date, asset type) executing the same `TradingAgentsGraph` pipeline in an isolated subprocess, with validation (ticker/date/key presence) *before* anything is spent.
4. **Decision log** — rendered view of `trading_memory.md`.
5. **Settings** — read-only view of effective config and per-provider key status (set / missing — never values).

### Architectural impact

- New top-level `webui/` package mirroring `cli/` — the core `tradingagents/` library is untouched.
- Runs execute as **subprocesses** (`python -m webui.runner`), which also sidesteps the documented module-level-config concurrency limitation (P2-05): each run owns its process.
- Status is exchanged through atomic JSON files in the existing results directory — no new storage, no daemon state to migrate.

### Security posture

- Binds `127.0.0.1` by default; binding other interfaces requires an explicit flag and prints a warning (no auth layer exists).
- All path components from URLs validated with the existing `safe_ticker_component` + strict date check.
- API keys reported as booleans only; report/log content HTML-escaped before client-side markdown rendering (LLM/news-derived text is untrusted).
- `Content-Security-Policy: default-src 'self'` — no external resources, no inline script execution beyond same-origin files.

### Estimated implementation effort

~1,200 lines (server ≈ 350, runner ≈ 120, run manager ≈ 130, frontend ≈ 600) plus tests and docs. Implemented in Phase C of this session.
