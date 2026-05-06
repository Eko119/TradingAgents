# TradingAgents — Project Handoff & Summary Document

> Generated after initial setup session on branch `claude/setup-and-build-PzVhw`.

---

## 1. Project Overview

**TradingAgents** is an open-source, multi-agent LLM financial trading framework (v0.2.4) that mirrors the structure of a real-world trading firm. Instead of a single model making all decisions, the system decomposes complex trading tasks into specialized AI agents — each playing a distinct professional role — that collaborate, debate, and reach a consensus trading decision for a given stock ticker and date.

**Primary purpose:** Research-grade automated market analysis and trade decision-making using large language models.

**Problem it solves:** Single-model LLM approaches to trading analysis are shallow and lack cross-validation. TradingAgents introduces a multi-agent pipeline with structured debate (bullish vs. bearish researchers), risk review, and a portfolio manager approval gate, producing far more nuanced and defensible outputs.

> **Disclaimer:** This framework is designed for research purposes only. It is not intended as financial, investment, or trading advice.

**Key capabilities:**
- Parallel specialized agent analysis (fundamentals, sentiment, news, technical)
- Structured researcher debate (bull vs. bear)
- Risk management evaluation before any trade is approved
- Support for 10+ LLM providers (OpenAI, Anthropic, Google, xAI, DeepSeek, Qwen, GLM, OpenRouter, Azure, Ollama)
- Persistent decision log with realized-return reflection
- LangGraph checkpoint resume (crash recovery)
- Interactive CLI with rich terminal UI
- Docker support for containerized deployment

---

## 2. Tech Stack & Architecture

### Languages & Runtime
| Component | Detail |
|---|---|
| Language | Python 3.10+ (tested on 3.11.15 and 3.12) |
| Package manager | [`uv`](https://github.com/astral-sh/uv) (lock file: `uv.lock`) |
| Build system | `setuptools` via `pyproject.toml` |

### Core Frameworks & Libraries
| Library | Role |
|---|---|
| `langgraph` | Agent graph orchestration and state machine |
| `langchain-core` | Base abstractions (chains, prompts, messages) |
| `langchain-openai` | OpenAI / Azure OpenAI LLM integration |
| `langchain-anthropic` | Anthropic Claude LLM integration |
| `langchain-google-genai` | Google Gemini LLM integration |
| `langchain-experimental` | Experimental LangChain components |
| `langgraph-checkpoint-sqlite` | SQLite-backed checkpoint persistence |
| `yfinance` | Market data retrieval (prices, fundamentals) |
| `stockstats` | Technical indicators (MACD, RSI, etc.) |
| `backtrader` | Backtesting engine |
| `pandas` | Data manipulation |
| `typer` | CLI framework |
| `questionary` | Interactive terminal prompts |
| `rich` | Terminal formatting and progress display |
| `redis` | Optional caching layer |
| `requests` / `parsel` | HTTP requests and web scraping |

### Architecture Overview

```
User (CLI / Python API)
        │
        ▼
 TradingAgentsGraph          ← main orchestrator (LangGraph StateGraph)
        │
        ├── Analyst Team (parallel nodes)
        │     ├── Fundamentals Analyst     ← company financials via yfinance
        │     ├── Sentiment Analyst        ← social sentiment scoring
        │     ├── News Analyst             ← macroeconomic event analysis
        │     └── Technical Analyst        ← MACD, RSI, chart patterns
        │
        ├── Researcher Team
        │     ├── Bullish Researcher       ← argues for buying
        │     └── Bearish Researcher       ← argues against buying (debate rounds)
        │
        ├── Research Manager              ← structured-output synthesis
        │
        ├── Trader Agent                  ← structured-output trade proposal
        │
        └── Risk Management → Portfolio Manager
                                          ← final approve/reject with rationale
```

**Data flow:** Each agent node reads from and writes to a shared `AgentState` dict threaded through the LangGraph. The graph is compiled once at startup and `propagate(ticker, date)` runs a full traversal, returning the final decision.

**Persistence layer:**
- Decision log: `~/.tradingagents/memory/trading_memory.md` (Markdown, always on)
- Checkpoints: `~/.tradingagents/cache/checkpoints/<TICKER>.db` (SQLite, opt-in via `--checkpoint`)

---

## 3. File & Directory Structure

```
TradingAgents/
│
├── pyproject.toml              # Project metadata, dependencies, CLI entry point
├── uv.lock                     # Fully pinned dependency lock file (source of truth)
├── requirements.txt            # Contains only "." — defers to pyproject.toml
├── main.py                     # Standalone Python usage example
├── test.py                     # Ad-hoc test runner entry point
│
├── tradingagents/              # Core library package
│   ├── __init__.py
│   ├── default_config.py       # DEFAULT_CONFIG dict — all tunable parameters
│   ├── agents/                 # Individual agent implementations
│   │   ├── analysts/           # Fundamentals, sentiment, news, technical agents
│   │   ├── researchers/        # Bullish/bearish researcher agents
│   │   ├── trader/             # Trader agent (structured output)
│   │   ├── risk_mgmt/          # Risk management agents
│   │   └── portfolio_manager/  # Portfolio manager (final decision)
│   ├── dataflows/              # Data retrieval and processing pipelines
│   │   └── ...                 # yfinance wrappers, news scrapers, sentiment feeds
│   ├── graph/
│   │   └── trading_graph.py    # TradingAgentsGraph class — compiles & runs the graph
│   └── llm_clients/            # Provider-specific LLM client factories
│       └── ...                 # OpenAI, Anthropic, Google, DeepSeek, etc.
│
├── cli/                        # Interactive CLI application
│   ├── main.py                 # Typer app; `tradingagents` entry point
│   ├── config.py               # CLI configuration wizard logic
│   ├── models.py               # Model selection and provider mapping
│   ├── announcements.py        # Startup announcements / version notices
│   ├── stats_handler.py        # Live progress/stats display
│   ├── utils.py                # Shared CLI utilities
│   └── static/
│       └── welcome.txt         # ASCII welcome banner
│
├── scripts/                    # Utility / maintenance scripts
├── tests/                      # Pytest test suite
│   └── ...                     # Unit, integration, smoke test markers
│
├── assets/                     # Images for README and documentation
│   └── cli/                    # CLI screenshot assets
│
├── .env.example                # Template: standard LLM provider API keys
├── .env.enterprise.example     # Template: Azure OpenAI / enterprise config
├── Dockerfile                  # Multi-stage Python 3.12-slim build
├── docker-compose.yml          # Compose for app + optional Ollama sidecar
├── .dockerignore
├── .gitignore
├── CHANGELOG.md                # Full version history
└── LICENSE
```

---

## 4. Setup & Installation Instructions

### Prerequisites

| Requirement | Version |
|---|---|
| Python | >= 3.10 (3.11 or 3.12 recommended) |
| `uv` | >= 0.5.0 (install via `pip install uv` or official installer) |
| At least one LLM provider API key | See list below |

### Step-by-step Local Setup

**1. Clone the repository**
```bash
git clone https://github.com/TauricResearch/TradingAgents.git
cd TradingAgents
```

**2. Install `uv` if not already present**
```bash
pip install uv
# or via the official installer:
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**3. Install all dependencies from the frozen lock file**
```bash
uv sync
```
This creates `.venv/` and installs all 112 packages at the exact versions pinned in `uv.lock`. No upgrades, no resolution drift.

**4. Configure API keys**
```bash
cp .env.example .env
# Edit .env and fill in your chosen LLM provider key(s)
```

Required — set **at least one** LLM provider key:
```
OPENAI_API_KEY=sk-...
GOOGLE_API_KEY=...
ANTHROPIC_API_KEY=sk-ant-...
XAI_API_KEY=...
DEEPSEEK_API_KEY=...
DASHSCOPE_API_KEY=...    # Qwen / Alibaba
ZHIPU_API_KEY=...        # GLM / Zhipu
OPENROUTER_API_KEY=...
ALPHA_VANTAGE_API_KEY=... # Optional: for premium financial data
```

For Azure OpenAI:
```bash
cp .env.enterprise.example .env.enterprise
# Fill in AZURE_OPENAI_API_KEY, AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_DEPLOYMENT_NAME
```

**5. Verify the installation**
```bash
uv run tradingagents --help
```

### Docker (Alternative)

```bash
cp .env.example .env       # add your API keys
docker compose run --rm tradingagents
```

With local Ollama models:
```bash
docker compose --profile ollama run --rm tradingagents-ollama
```

---

## 5. Current State & What Was Accomplished

### Session Summary

This session performed the **initial environment setup** for the forked repository on branch `claude/setup-and-build-PzVhw`:

| Task | Status |
|---|---|
| Scanned and documented full repository structure | ✅ Complete |
| Identified tech stack and canonical toolchain (`uv`) | ✅ Complete |
| Installed all 112 dependencies from `uv.lock` (frozen) | ✅ Complete |
| Verified CLI entry point (`tradingagents --help`) | ✅ Complete |
| Committed updated `uv.lock` to `claude/setup-and-build-PzVhw` | ✅ Complete |
| Pushed branch to remote (`origin/claude/setup-and-build-PzVhw`) | ✅ Complete |

### What is Fully Functional (upstream, v0.2.4)

- **Multi-agent pipeline**: All analyst, researcher, trader, and risk/portfolio agents are implemented and wired into the LangGraph state graph.
- **10+ LLM providers**: OpenAI (incl. GPT-5.4 family), Anthropic (Claude 4.x), Google (Gemini 3.x), xAI (Grok 4.x), DeepSeek (V4 with thinking-mode), Qwen, GLM, OpenRouter, Azure OpenAI, Ollama.
- **Structured outputs**: Research Manager, Trader, and Portfolio Manager use structured-output LLM calls for deterministic JSON responses.
- **Decision log**: Persistent Markdown log at `~/.tradingagents/memory/trading_memory.md` — records decisions, realized returns, and cross-ticker lessons.
- **Checkpoint resume**: LangGraph SQLite checkpoints allow crashed runs to resume from the last successful node.
- **Interactive CLI**: Rich terminal UI with provider selection, model catalog, research-depth slider, date picker, and live agent-progress display.
- **Docker**: Multi-stage build producing a minimal, non-root image; Ollama sidecar profile for local models.
- **Backtesting**: `backtrader` integration available for historical strategy evaluation.

### Key Implementation Detail: Lock File Update

During `uv sync`, the `uv.lock` file was updated. `uv` rewrote the lock file's internal representation to match the resolver's output for Python 3.11 (the environment's interpreter). No package versions were changed — only the lock file format was normalized. This change was committed in `b410a1f`.

---

## 6. Usage Guide

### Interactive CLI

```bash
uv run tradingagents
```

The CLI wizard prompts for:
- **Ticker**: e.g., `NVDA`, `AAPL`, `TSLA`
- **Analysis date**: historical date for the analysis
- **LLM provider**: select from the supported list
- **Model**: choose reasoning depth (quick vs. deep think)
- **Research depth**: number of analyst/researcher debate rounds
- **Checkpoint**: opt-in to crash recovery

Options:
```bash
uv run tradingagents --checkpoint          # Enable checkpoint/resume
uv run tradingagents --clear-checkpoints   # Reset all saved checkpoints
```

### Python API

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

# Basic usage
ta = TradingAgentsGraph(debug=True, config=DEFAULT_CONFIG.copy())
_, decision = ta.propagate("NVDA", "2026-01-15")
print(decision)
```

Custom configuration:
```python
config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "anthropic"         # or "openai", "google", "deepseek", etc.
config["deep_think_llm"] = "claude-sonnet-4-6"
config["quick_think_llm"] = "claude-haiku-4-5-20251001"
config["max_debate_rounds"] = 2
config["checkpoint_enabled"] = True

ta = TradingAgentsGraph(debug=True, config=config)
_, decision = ta.propagate("AAPL", "2026-03-01")
```

See `tradingagents/default_config.py` for all tunable parameters.

### Running Tests

```bash
uv run pytest                           # All tests
uv run pytest -m unit                   # Fast unit tests only
uv run pytest -m smoke                  # Quick sanity checks
uv run pytest -m integration            # Tests requiring external services
```

---

## 7. Known Issues & Limitations

1. **No API keys = immediate failure**: The framework has no graceful degradation when API keys are missing. The process will raise an authentication error at runtime, not at startup.

2. **`redis` dependency but no required Redis server**: `redis` is listed as a dependency, but the framework does not mandate a running Redis instance for basic operation. Configuration for Redis-based caching is not fully documented.

3. **`requirements.txt` is a stub**: The file contains only `.` — it is not a traditional frozen requirements file. Users expecting `pip install -r requirements.txt` to install exact pinned versions will not get deterministic installs unless they also use `uv sync`.

4. **Python 3.13 in README, 3.11 in environment**: The README suggests `python=3.13` for conda, but the project specifies `>=3.10`. The lock file was resolved against Python 3.11.15 in this environment; there may be minor differences if re-resolved against 3.13.

5. **Financial data availability**: `yfinance` may return incomplete or rate-limited data for certain tickers or historical dates. Analysis quality degrades silently when data is sparse.

6. **Non-determinism**: LLM outputs are inherently non-deterministic. The same ticker and date may produce different trading decisions across runs, even with identical configuration.

7. **Alpha Vantage integration is optional but undocumented in depth**: `ALPHA_VANTAGE_API_KEY` is listed in `.env.example` but the degree to which premium data improves results is not benchmarked.

8. **No `.env` validation at startup**: The CLI does not validate that a required API key for the selected provider is set before beginning the (potentially long-running) multi-agent pipeline.

---

## 8. Next Steps & Future Improvements

### High Priority

- [ ] **Add `.env` / API key validation at CLI startup** — fail fast with a clear error message before any agents are invoked, saving wasted time and API credits.
- [ ] **Pin `requirements.txt` to frozen versions** — generate a proper `pip`-compatible frozen requirements file (e.g., `uv pip compile pyproject.toml -o requirements.txt`) so non-`uv` users also get deterministic installs.
- [ ] **Expand test coverage** — the `tests/` directory exists but coverage of agent logic, data flows, and graph traversal appears minimal. Add unit tests for at least the data retrieval layer and structured-output parsers.

### Medium Priority

- [ ] **Startup health check** — before running the pipeline, verify network connectivity to the chosen LLM provider and data sources, with actionable error messages.
- [ ] **Redis integration documentation** — clarify when Redis is used (caching, rate-limiting) and how to configure or disable it.
- [ ] **Backtesting workflow guide** — `backtrader` is a dependency but a concrete end-to-end backtesting example (using the framework's decisions as signals) is missing from the docs.
- [ ] **CI/CD pipeline** — add a GitHub Actions workflow running `uv sync && pytest -m unit` on every push to catch regressions early.
- [ ] **Provider fallback strategy** — if one LLM provider times out or rate-limits, optionally fall back to a secondary provider without interrupting the run.

### Low Priority / Research

- [ ] **Benchmark LLM provider quality** — systematic comparison of decision quality and cost across providers (OpenAI vs. Anthropic vs. Google vs. DeepSeek) for the same ticker/date pairs.
- [ ] **Structured logging** — replace `print`/`rich` output with structured JSON logs to enable downstream analytics pipelines.
- [ ] **Web UI** — a lightweight dashboard (e.g., Streamlit or FastAPI + React) over the Python API for non-CLI users.
- [ ] **Portfolio-level analysis** — extend `propagate()` to accept a basket of tickers and produce a portfolio-level allocation recommendation, not just individual buy/sell signals.

---

*Document generated from session `claude/setup-and-build-PzVhw` — branch contains the initial dependency installation and lock file normalization commit (`b410a1f`).*
