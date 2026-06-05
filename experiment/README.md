# TradingAgents evaluation harness

Run TradingAgents as a **quantitative experiment**, not a trading account. The
goal of milestone #1 is *not* profit — it's evidence:

> Can I show, on independent calls, that the system's directional calls beat a
> coin flip **and** beat SPY, with statistical significance?

Everything here is **paper only**. No order is ever placed.

## Pipeline

| Step | Command | What it does |
|------|---------|--------------|
| Generate | `python -m experiment.run` | Runs the fixed universe for today, archives every full report to `predictions/<date>/<SYMBOL>.md`, appends one row per symbol to `predictions/predictions.csv` (Status=`pending`). |
| Score | `python -m experiment.score` | For predictions whose 7d/30d window has elapsed, fills forward returns vs SPY and marks them `scored`. Safe to run repeatedly. |
| Review | `python -m experiment.review` | Hit-rate + binomial p-value, mean excess vs SPY, and (clearly fenced) calibration slices. |
| Nightly | `experiment/nightly.sh` | run → score → review, for cron. |

Set the universe in `experiment/universe.txt` (keep it **stable**). Override per
run with `--symbols AAPL NVDA` or `--date 2026-06-05`. `--dry-run` checks wiring
without LLM calls.

## Prerequisites

- An LLM provider key in the environment (e.g. `OPENAI_API_KEY`), via `.env`.
- Deps installed (`uv sync`). `yfinance` (already a dep) provides prices/SPY.

## What gets logged (and what TradingAgents actually emits)

TradingAgents' final decision is a **5-tier rating**
(Buy/Overweight/Hold/Underweight/Sell), mapped to a score `+2..-2`. It does
**not** emit a numeric per-trade confidence. The only confidence signal in the
system is on the **Sentiment Analyst** report (`low/medium/high`, plus a 0–10
sentiment score) — we log it as `SentimentConfidence`, but it measures
*sentiment data quality*, not the model's conviction in the trade. Don't
over-read it.

`CallCorrect` = the directional call paid off **relative to SPY** (long right
when excess > 0, short right when excess < 0). Holds are excluded from hit-rate.

## Read the results honestly — five traps this harness tries to keep you out of

1. **Forward test only.** Never run `--date` on a *past* date and call it a
   backtest: the LLM already knows what happened then (training leakage). Only
   predictions recorded *before* the outcome existed are valid.
2. **Alpha, not beta.** A long, tech-heavy basket beats SPY in any bull market —
   that's market exposure, not skill. The headline metric is the *directional*
   hit-rate and *excess* return vs SPY, not raw return.
3. **Effective sample ≪ row count.** Correlated names (the default universe is
   tech-heavy) and same-day calls mean 100 rows can be ~15 independent bets.
   `review.py` warns when one date dominates. Diversify `universe.txt` across
   uncorrelated sectors.
4. **Slices are hypothesis-generating only.** Cut a small sample by
   sector × confidence and spurious "67% vs 39%" tables appear from noise. Any
   pattern must survive a *fresh* batch before you trust it.
5. **Cost & determinism.** Each symbol = the full agent graph (dozens of LLM
   calls). Runs are billed and slow; `temperature=0` (default) keeps re-runs
   reproducible.

## Only after the evidence exists

Promote to a tiny real-money trial **only** once you have 100+ independent
predictions with a hit-rate significantly above 50% and positive mean excess vs
SPY. Then size by risk (e.g. 1% per trade), treating it as validation, not
income.
