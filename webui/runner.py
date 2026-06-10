"""Headless analysis runner executed as a subprocess of the web console.

Runs one ``TradingAgentsGraph.propagate`` and persists the same artifacts
the CLI produces (``reports/*.md``) plus a ``web_run.json`` status file the
console polls. Runs in its own process so a crash, an unhandled provider
error, or the module-level dataflow config never affect the server or a
concurrent run.

Status file transitions: ``running`` -> ``completed`` | ``failed``.
All writes are atomic (temp file + replace) so the poller never reads a
half-written document.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import traceback
from datetime import datetime, timezone
from pathlib import Path

STATUS_FILENAME = "web_run.json"

# final_state keys persisted as report sections, in display order.
# Mirrors the sections the CLI writes for the same run.
REPORT_SECTIONS = (
    "market_report",
    "sentiment_report",
    "news_report",
    "fundamentals_report",
    "investment_plan",
    "trader_investment_plan",
    "final_trade_decision",
)


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_atomic(path: Path, text: str) -> None:
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def write_status(run_dir: Path, **fields) -> None:
    path = run_dir / STATUS_FILENAME
    current = {}
    if path.exists():
        try:
            current = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            current = {}
    current.update(fields)
    _write_atomic(path, json.dumps(current, indent=2))


def run_analysis(ticker: str, date: str, asset_type: str, run_dir: Path) -> int:
    """Execute one analysis; returns a process exit code."""
    write_status(
        run_dir,
        status="running",
        ticker=ticker,
        date=date,
        asset_type=asset_type,
        started_at=_utcnow(),
        pid=os.getpid(),
    )
    try:
        # Imports deferred so a broken environment is reported through the
        # status file instead of a stack trace nobody sees.
        from tradingagents.default_config import DEFAULT_CONFIG
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        config = DEFAULT_CONFIG.copy()
        graph = TradingAgentsGraph(debug=False, config=config)
        final_state, decision = graph.propagate(ticker, date, asset_type=asset_type)

        reports_dir = run_dir / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        for section in REPORT_SECTIONS:
            content = final_state.get(section)
            if content:
                _write_atomic(reports_dir / f"{section}.md", str(content))

        write_status(
            run_dir,
            status="completed",
            finished_at=_utcnow(),
            decision=str(decision),
        )
        return 0
    except BaseException as exc:  # noqa: BLE001 — terminal report, then re-raise intent via exit code
        write_status(
            run_dir,
            status="failed",
            finished_at=_utcnow(),
            error=f"{type(exc).__name__}: {exc}",
        )
        traceback.print_exc()
        return 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Headless TradingAgents analysis run")
    parser.add_argument("ticker")
    parser.add_argument("date", help="Analysis date, YYYY-MM-DD")
    parser.add_argument("--asset-type", default="stock", choices=["stock", "crypto"])
    parser.add_argument("--run-dir", required=True, help="Directory for status + reports")
    args = parser.parse_args(argv)

    run_dir = Path(args.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_analysis(args.ticker, args.date, args.asset_type, run_dir)


if __name__ == "__main__":
    sys.exit(main())
