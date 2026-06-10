# Testing Report — TradingAgents

> Executed 2026-06-10 on branch `claude/production-readiness-audit-2x1h21`, Python 3.11.15, `uv`-managed venv from `uv.lock`.

## Results (actual output)

```
uv run pytest
312 passed, 1 skipped, 7 warnings, 75 subtests passed in 14.10s
```

- The single skip is `tests/test_deepseek_reasoning.py:210` — a live-API integration test that self-skips when `DEEPSEEK_API_KEY` is absent. Expected in CI.
- `make test-unit` (`pytest -m unit`): 174 passed, 139 deselected.
- `uv lock --check`: lock file consistent with `pyproject.toml`.
- `uv build`: sdist + wheel build cleanly.
- `uv run tradingagents --help`: CLI entry point loads.

## What changed this session

- **Fixed:** the suite was previously unrunnable from a clean checkout — `pytest` was not a declared dependency, so `uv run pytest` resolved to a system pytest without project packages. `pytest>=8.0` is now a dev dependency and `uv.lock` was re-resolved (it was also stale vs `pyproject.toml`).
- **Added:** `tests/test_alpha_vantage_request_timeout.py` — regression coverage for the request-timeout fix (2 tests).
- **Added:** GitHub Actions CI (`.github/workflows/ci.yml`) running the suite on Python 3.10/3.11/3.12 for every push/PR.

## Critical paths covered (existing suite, 29 test files)

| Area | Files |
|---|---|
| Graph orchestration & resume | `test_analyst_execution.py`, `test_checkpoint_resume.py`, `test_signal_processing.py` |
| Structured agent outputs | `test_structured_agents.py`, `test_model_validation.py` |
| LLM client matrix (capabilities, keys, provider quirks) | `test_capabilities.py`, `test_api_key_env.py`, `test_anthropic_effort.py`, `test_deepseek_reasoning.py`, `test_minimax.py`, `test_google_api_key.py`, `test_ollama_base_url.py`, `test_temperature_config.py` |
| Data integrity / no-hallucination guards | `test_no_data_handling.py`, `test_market_data_validator.py`, `test_instrument_identity.py`, `test_stockstats_date_column.py` |
| Input/path safety | `test_safe_ticker_component.py`, `test_ticker_symbol_handling.py`, `test_symbol_utils.py` |
| Config & env overrides | `test_env_overrides.py`, `test_dataflows_config.py`, `test_cli_env_skip.py` |
| Persistence | `test_memory_log.py` |
| Vendor fallbacks | `test_reddit_fallback.py`, `test_crypto_asset_mode.py` |
| Network hardening (new) | `test_alpha_vantage_request_timeout.py` |

Hermeticity: `tests/conftest.py` injects placeholder API keys and mocks LLM clients, so the suite is deterministic and offline-safe.

## Known gaps

1. **End-to-end pipeline runs are not automated** — a full `propagate()` requires live LLM + market-data APIs (cost, nondeterminism). Mitigation: the graph wiring, signal processing, and structured-output layers are unit-tested with mocks; `scripts/smoke_structured_output.py` exists for manual live smoke testing.
2. **No coverage measurement** — `pytest-cov` is not configured; coverage is assessed by area, not percentage.
3. **CLI interactive flows** are partially tested (`test_cli_env_skip.py`); the questionary prompt paths are exercised manually only.
4. **Docker image** is built but not exercised in CI (no registry/runtime in the pipeline).

## Remaining risks

- LLM nondeterminism means semantic regression in agent quality is not catchable by unit tests.
- Data-vendor schema drift (yfinance/Alpha Vantage) surfaces at runtime; the no-data guards convert this to explicit degradation rather than wrong numbers.
