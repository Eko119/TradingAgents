# Production Readiness Plan — TradingAgents

> Derived from `REPOSITORY_ANALYSIS.md` (2026-06-10). Status legend: `[ ]` not started, `[-]` in progress, `[x]` complete.

## P0 — Critical

### [x] P0-01 — Test suite unrunnable from a clean checkout
- **Problem:** `uv run pytest` failed with `ModuleNotFoundError` for every project dependency.
- **Root cause:** `pytest` was never declared (no dev-dependency group), so `uv run` fell through to a system-level pytest outside the project venv. Additionally `uv.lock` was stale relative to `pyproject.toml` (locked `yfinance 0.2.63` vs required `>=1.4.1`).
- **Solution:** `uv add --dev pytest>=8.0`; re-resolve and commit `uv.lock`.
- **Expected impact:** `uv sync && uv run pytest` works deterministically on any machine.
- **Validation:** `uv run pytest` → 310 passed, 1 skipped (live-API test), 75 subtests. ✅ Verified.

## P1 — High

### [x] P1-01 — No CI pipeline
- **Problem:** No automated verification on push; regressions reach `main` silently.
- **Root cause:** `.github/workflows/` absent.
- **Solution:** GitHub Actions workflow: `uv sync --locked` + `uv run pytest` on Python 3.10/3.11/3.12, on push and PR.
- **Expected impact:** every change validated against the full unit suite.
- **Validation:** workflow file added; runs on next push.

### [x] P1-02 — Unbounded network call can hang the pipeline
- **Problem:** `requests.get(API_BASE_URL, params=...)` in `tradingagents/dataflows/alpha_vantage_common.py:79` has no `timeout`.
- **Root cause:** `requests` defaults to no timeout; a stalled TCP connection blocks the analysis forever.
- **Solution:** add a module-level `REQUEST_TIMEOUT = 30` and pass `timeout=REQUEST_TIMEOUT`.
- **Expected impact:** vendor stalls surface as a catchable `requests.Timeout` instead of an indefinite hang.
- **Validation:** new unit test asserts the timeout is passed; full suite green.

### [x] P1-03 — Results path built from unvalidated user input (defense-in-depth)
- **Problem:** `cli/main.py:1037` interpolates `selections["ticker"]` and `selections["analysis_date"]` into the results path without `safe_ticker_component`.
- **Root cause:** CLI prompt regexes currently prevent traversal, but nothing protects against a future refactor or programmatic caller bypassing the prompts.
- **Solution:** validate both components with `safe_ticker_component` (already used by dataflows/checkpointer) at the point of path construction.
- **Expected impact:** path traversal structurally impossible regardless of input source.
- **Validation:** existing `test_safe_ticker_component.py` covers the validator; full suite green.

## P2 — Medium

### [x] P2-01 — Silent failure in announcements fetch
- **Problem/Root cause:** `cli/announcements.py:23` catches `Exception` with no logging.
- **Solution:** log the failure at debug level via `logging` before returning the fallback.
- **Validation:** suite green; behavior otherwise unchanged (graceful fallback retained).

### [x] P2-02 — `print()` instead of logging for data-quality warning
- **Problem/Root cause:** `alpha_vantage_common.py:134` prints a CSV-filter failure to stdout, invisible in logs and mixed into rich CLI output.
- **Solution:** module logger + `logger.warning(...)`.
- **Validation:** suite green.

### [x] P2-03 — Checkpoint clearing swallows DB errors
- **Problem/Root cause:** `checkpointer.clear_checkpoint` does `except sqlite3.OperationalError: pass`, hiding corruption/permission problems.
- **Solution:** log a warning with the DB path and error.
- **Validation:** `test_checkpoint_resume.py` green.

### [x] P2-04 — CLI crashes if `welcome.txt` missing from package
- **Problem/Root cause:** unguarded `open()` at `cli/main.py:469`; broken packaging kills the CLI before any useful error.
- **Solution:** fall back to a plain-text title when the asset can't be read.
- **Validation:** suite green; manual check of fallback path.

### [ ] P2-05 — Module-level mutable dataflow config (documented, not refactored)
- **Problem:** `tradingagents/dataflows/config.py` holds process-global config; two concurrent `TradingAgentsGraph` instances with different configs in one process would interfere.
- **Root cause:** historical design; every dataflow reads the module global.
- **Decision:** **document** rather than refactor — touching every dataflow call-site is high-risk for zero benefit in the supported single-analysis-per-process model. Re-visit only if in-process concurrency becomes a requirement.
- **Validation:** risk documented in `REPOSITORY_ANALYSIS.md` §10 and `RELEASE_READINESS_REPORT.md`.

## P3 — Nice-to-have

### [x] P3-01 — One-command developer entry points
- **Problem:** onboarding requires knowing the `uv` incantations.
- **Solution:** `Makefile` with `setup` / `test` / `run` / `docker` targets (thin wrappers, no new logic).
- **Validation:** `make test` runs the suite.

## Session 2 — verification audit additions (see VERIFICATION_AUDIT.md)

### [x] S2-01 — Dependency CVE remediation (P1)
13 locked packages with known CVEs upgraded (urllib3, langgraph 1.x, langchain-core, langsmith, aiohttp, idna, lxml, marshmallow, orjson, protobuf, pyasn1, pygments, python-dotenv); `pip-audit` vs exported lock now clean; non-blocking CI audit job added. Validation: full suite green on upgraded stack.

### [x] S2-02 — XML entity-expansion hardening (P2)
Reddit RSS fallback: 5 MiB cap + DTD/ENTITY rejection before `ET.fromstring`; 3 regression tests.

### [x] S2-03 — Web Console (revises session-1 "no GUI" decision)
`webui/` localhost dashboard (results browser, run launcher with subprocess isolation, decision log, settings) — zero new dependencies, 27 tests. See GUI_FEASIBILITY_ANALYSIS.md, DESIGN_SYSTEM.md.

### [ ] S2-04 — Docker image build validation (P1, blocked here)
No Docker daemon in the validation environment (verified: `docker info` fails); image has never been built. Run `docker build .` + a compose smoke on a Docker-capable host.

### [ ] P3-02 — Structured JSON logging across agents
- **Decision:** deferred — rich CLI output is the product surface; converting it wholesale is a feature project, not hardening. Logging added where errors were previously silent (P2-01/02/03).

### [ ] P3-03 — Dockerfile HEALTHCHECK
- **Decision:** rejected — the container runs an interactive CLI, not a daemon; a health check has nothing meaningful to probe. Documented in `REPOSITORY_ANALYSIS.md` §9.
