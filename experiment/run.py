"""Step 3+4: run TradingAgents over the fixed universe for one date, archive
every full report, and append a row per symbol to the prediction ledger.

Usage:
    python -m experiment.run                 # today, full universe
    python -m experiment.run --date 2026-06-05
    python -m experiment.run --symbols AAPL NVDA
    python -m experiment.run --dry-run       # no LLM calls; checks wiring

Requires an LLM provider API key in the environment (e.g. OPENAI_API_KEY).
This is PAPER ONLY — it never places a trade.
"""

from __future__ import annotations

import argparse
import sys
import traceback
from datetime import date as date_cls
from pathlib import Path

from experiment import cost, store
from experiment.extract import extract_fields

PRED_DIR = store.PRED_DIR


def _archive_report(run_date: str, symbol: str, final_state: dict, rating: str) -> Path:
    """Write the full report to predictions/<date>/<SYMBOL>.md. Never overwrite."""
    day_dir = PRED_DIR / run_date
    day_dir.mkdir(parents=True, exist_ok=True)
    path = day_dir / f"{symbol}.md"
    if path.exists():
        # Preserve evidence: append a numbered sibling instead of clobbering.
        i = 2
        while (day_dir / f"{symbol}_{i}.md").exists():
            i += 1
        path = day_dir / f"{symbol}_{i}.md"

    sections = [
        f"# {symbol} — {run_date}",
        f"\n**Final Rating:** {rating}\n",
        "## Final Trade Decision\n" + (final_state.get("final_trade_decision", "") or ""),
        "## Investment Plan (Research Manager)\n" + (final_state.get("investment_plan", "") or ""),
        "## Trader Plan\n" + (final_state.get("trader_investment_plan", "") or ""),
        "## Market Report\n" + (final_state.get("market_report", "") or ""),
        "## Sentiment Report\n" + (final_state.get("sentiment_report", "") or ""),
        "## News Report\n" + (final_state.get("news_report", "") or ""),
        "## Fundamentals Report\n" + (final_state.get("fundamentals_report", "") or ""),
    ]
    path.write_text("\n\n".join(sections), encoding="utf-8")
    return path


def run(run_date: str, symbols, *, dry_run: bool, skip_existing: bool) -> int:
    store.ensure_store()
    errors = 0

    if dry_run:
        print(f"[dry-run] would run {len(symbols)} symbols for {run_date}: {', '.join(symbols)}")
        return 0

    # Imported lazily so --dry-run works without deps/keys configured.
    from langchain_core.callbacks import get_usage_metadata_callback
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    from tradingagents.default_config import DEFAULT_CONFIG

    config = DEFAULT_CONFIG.copy()
    # Reproducibility: pin temperature unless the env already set one.
    config.setdefault("temperature", 0.0)
    ta = TradingAgentsGraph(debug=False, config=config)

    run_cost = 0.0
    run_in = run_out = 0
    for sym in symbols:
        if skip_existing and store.has_prediction(run_date, sym):
            print(f"  = {sym}: already logged for {run_date}, skipping")
            continue
        try:
            print(f"  > {sym}: running ...", flush=True)
            with get_usage_metadata_callback() as usage_cb:
                final_state, rating = ta.propagate(sym, run_date)
            usage = cost.summarize(usage_cb.usage_metadata)
            run_cost += usage["cost"] or 0.0
            run_in += usage["input"]
            run_out += usage["output"]

            report_path = _archive_report(run_date, sym, final_state, rating)
            try:
                as_of = store.close_on_or_before(sym, run_date)
            except Exception:
                as_of = None  # price is best-effort; never block logging the call

            fields = extract_fields(final_state, rating)
            row = {
                "Date": run_date,
                "Symbol": sym,
                "AsOfPrice": "" if as_of is None else round(as_of, 4),
                "ReportPath": str(report_path.relative_to(store.REPO_ROOT)),
                "InputTokens": usage["input"],
                "OutputTokens": usage["output"],
                "EstCostUSD": "" if usage["cost"] is None else usage["cost"],
                "Status": "pending",
                **fields,
            }
            store.append_row(row)
            print(f"    -> {rating} (score {row['Score']})  {cost.fmt(usage)}  saved {row['ReportPath']}")
        except Exception as exc:  # keep the batch going; record the failure
            errors += 1
            store.append_row({
                "Date": run_date, "Symbol": sym, "Status": "error",
                "Notes": f"{type(exc).__name__}: {exc}"[:300],
            })
            print(f"    !! {sym} failed: {type(exc).__name__}: {exc}", file=sys.stderr)
            traceback.print_exc()

    cost_str = f"~${run_cost:.2f}" if run_cost else "$? (set experiment/prices.json)"
    print(f"\nRun total: {run_in:,} in / {run_out:,} out tokens  {cost_str}")
    return errors


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Run TradingAgents over the fixed universe (paper only).")
    p.add_argument("--date", default=date_cls.today().isoformat(), help="As-of date YYYY-MM-DD (default: today)")
    p.add_argument("--symbols", nargs="*", help="Override the universe with specific tickers")
    p.add_argument("--universe", type=Path, default=None, help="Path to a universe file")
    p.add_argument("--dry-run", action="store_true", help="Print plan; make no LLM calls")
    p.add_argument("--no-skip", action="store_true", help="Re-run symbols already logged for this date")
    args = p.parse_args(argv)

    symbols = [s.upper() for s in args.symbols] if args.symbols else store.load_universe(args.universe)
    if not symbols:
        print("No symbols to run.", file=sys.stderr)
        return 2

    errors = run(args.date, symbols, dry_run=args.dry_run, skip_existing=not args.no_skip)
    if errors:
        print(f"\nCompleted with {errors} error(s). See predictions.csv rows with Status=error.")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
