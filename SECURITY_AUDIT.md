# Security Audit — TradingAgents

> Performed 2026-06-10. Scope: full source (`tradingagents/`, `cli/`, `scripts/`), Dockerfile, docker-compose, dependency declarations. Method: manual code review plus targeted greps for missing timeouts, bare excepts, secret leakage, `eval`/`pickle`, disabled TLS, SQL string interpolation, and path construction from user input.

## Threat model

A CLI/library run locally or in Docker by a single operator. Inputs that cross a trust boundary:
1. **User CLI input** (ticker, date, model names)
2. **LLM tool-call arguments** — indirectly attacker-influenced via prompt injection in fetched news/social content
3. **External API responses** (yfinance, Alpha Vantage, Reddit, StockTwits, announcement endpoint)
4. **Environment / .env secrets** (provider API keys)

There is no server surface: no listening sockets, no authn/authz layer, no sessions, no HTML rendering — XSS/CSRF/SSRF-via-user-URL classes do not apply. The closest analogue is #2: LLM-supplied tool arguments must be treated as untrusted, and they are (see below).

## Findings & fixes (this session)

| ID | Severity | Finding | Status |
|----|----------|---------|--------|
| SEC-1 | P1 (availability) | `requests.get` without `timeout` in `tradingagents/dataflows/alpha_vantage_common.py` — stalled vendor connection hangs the pipeline indefinitely | **Fixed** — `timeout=30`, regression-tested |
| SEC-2 | P1 (defense-in-depth) | CLI results directory built from raw `ticker`/`date` input (`cli/main.py`); traversal was prevented only by prompt regexes upstream | **Fixed** — `safe_ticker_component()` enforced at path construction |
| SEC-3 | P2 (observability) | Fully silent `except Exception` in `cli/announcements.py` could mask TLS/connectivity failures | **Fixed** — failure now logged |
| SEC-4 | P2 (observability) | `clear_checkpoint` silently swallowed `sqlite3.OperationalError` (corruption/permissions invisible) | **Fixed** — warning logged |

## Verified non-findings

- **Secrets:** API keys are read from env vars via a canonical mapping (`tradingagents/llm_clients/api_key_env.py`); interactive entry uses `questionary.password` (no echo); keys are persisted only to the local `.env`; no key appears in logs, exceptions, or repr output. `.env` and `.env.enterprise` are gitignored; `.env.example` contains placeholders only.
- **Injection:** checkpoint SQLite access uses parameterized queries; the only f-string in SQL interpolates a hardcoded table-name tuple. No `eval`, `exec`, unpickling of external data, or shell-out with user input anywhere in the codebase.
- **Path traversal:** `safe_ticker_component()` (allowlist regex + dots-only rejection, `tests/test_safe_ticker_component.py`) guards cache, checkpoint, and — as of this audit — CLI results paths. LLM tool-call tickers (trust boundary #2) pass through the same guard in dataflows.
- **TLS:** no `verify=False` anywhere; requests use default certificate validation.
- **Untrusted LLM/tool content:** market-data validation layer (`market_data_validator.py`, instrument-identity resolution) grounds numeric claims in fetched data; fetched news/social text is passed to LLMs as content, never executed or interpolated into commands/paths.
- **Docker:** multi-stage build, non-root `appuser`, no secrets baked into the image (`.env` is injected at runtime via `env_file`), writable state confined to a named volume.
- **Insecure defaults:** none found; checkpointing is opt-in, no default credentials exist.

## Dependency posture

> **Correction (session 2):** the original wording below understated risk — a proper `pip-audit` of the exported lock file found **15+ known CVEs** across 13 packages (urllib3 ×6, langgraph, langchain-core, langsmith, aiohttp, idna, lxml, marshmallow, orjson, protobuf, pyasn1, pygments, python-dotenv). All were upgraded in `uv.lock` with the full test suite passing, and the final scan reports **"No known vulnerabilities found."** A non-blocking `dependency-audit` job now runs in CI. Methodology note: `uvx pip-audit` with no arguments audits its own venv and returns a false clean — always audit the exported lock (`uv export … | pip-audit -r`).

- All 120 packages pinned in `uv.lock`; CI installs with `uv sync --locked` so resolution cannot drift.

### Session 2 additions

- **bandit** static scan: 0 high-severity; 6 medium triaged — 4 false positives (parameterized SQL with hardcoded table tuple; the literal word "select" in an LLM prompt), 1 accepted (B310: `urlopen` on fixed `https://` templates), 1 fixed:
- **Fixed — XML entity-expansion exposure** (`tradingagents/dataflows/reddit.py`, bandit B314): the RSS fallback parsed fetched XML with `ET.fromstring`. Now capped at 5 MiB and any feed containing `<!DOCTYPE`/`<!ENTITY` is rejected before parsing (a legitimate Atom feed never carries a DTD). Zero new dependencies; regression-tested.
- **Web console surface** (new in session 2): binds `127.0.0.1` by default and warns loudly on other binds (no auth layer); URL path components re-validated with `safe_ticker_component` + strict date regex; API keys exposed as booleans only (tested: a set key value never appears in any response byte); `Content-Security-Policy: default-src 'self'`, `X-Content-Type-Options: nosniff`, `frame-ancestors 'none'`; static file allowlist (no directory serving); report/log content HTML-escaped client-side before markdown rendering (LLM/news-derived text is untrusted); 64 KiB POST body cap; runs launched via argument-list `subprocess` (no shell).

## Remaining risks & recommendations

1. **Prompt injection in fetched content** can bias agent *conclusions* (not code execution). Inherent to LLM agents; mitigated by grounding/validation layers. Treat outputs as research, not execution signals.
2. **`.env` on disk in plaintext** — standard for local tooling; use a secrets manager if running unattended in shared infrastructure.
3. **Announcement endpoint** (`cli/announcements.py`) fetches remote text displayed in the terminal; content is rendered via rich markup only, fetched over HTTPS, with a timeout and graceful fallback. Risk accepted (display-only).
4. **Dependency CVE monitoring** not yet automated (see above).
