"""CSV-backed prediction store + market-data helpers.

Append-only ledger at predictions/predictions.csv. One row per (Date, Symbol)
prediction. Forward-return columns start empty and are filled in later by
score.py once the holding window has matured — that separation is what keeps
the experiment honest: the prediction is committed before the outcome exists.
"""

from __future__ import annotations

import csv
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

# predictions/ lives at repo root next to this package.
REPO_ROOT = Path(__file__).resolve().parent.parent
PRED_DIR = REPO_ROOT / "predictions"
CSV_PATH = PRED_DIR / "predictions.csv"

BENCHMARK = "SPY"

# Column order is the contract. Anything appended must keep these stable so
# old rows stay readable.
COLUMNS: List[str] = [
    "Date",            # prediction (as-of) date, YYYY-MM-DD
    "Symbol",
    "AsOfPrice",       # close on/just before Date (entry reference)
    "Rating",          # Buy/Overweight/Hold/Underweight/Sell
    "Score",           # +2..-2
    "Direction",       # +1 long / 0 / -1 short
    "SentimentBand",
    "SentimentScore",  # 0-10
    "SentimentConfidence",  # low/medium/high (sentiment data quality, NOT trade confidence)
    "PriceTarget",
    "TimeHorizon",
    "ThesisSummary",
    "ReportPath",      # relative path to archived full report
    "InputTokens",     # provider-reported prompt tokens for this prediction
    "OutputTokens",    # provider-reported completion tokens
    "EstCostUSD",      # estimated cost from experiment/cost.py price table
    "Status",          # pending | scored | error
    # --- filled later by score.py ---
    "Px_7d", "Ret_7d", "SPY_Ret_7d", "Excess_7d", "BeatSPY_7d", "CallCorrect_7d",
    "Px_30d", "Ret_30d", "SPY_Ret_30d", "Excess_30d", "BeatSPY_30d", "CallCorrect_30d",
    "Notes",
]


def ensure_store() -> None:
    PRED_DIR.mkdir(parents=True, exist_ok=True)
    if not CSV_PATH.exists():
        with CSV_PATH.open("w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=COLUMNS).writeheader()


def read_rows() -> List[Dict[str, str]]:
    if not CSV_PATH.exists():
        return []
    with CSV_PATH.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_rows(rows: List[Dict[str, str]]) -> None:
    ensure_store()
    with CSV_PATH.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in COLUMNS})


def append_row(row: Dict[str, object]) -> None:
    ensure_store()
    with CSV_PATH.open("a", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore").writerow(
            {c: row.get(c, "") for c in COLUMNS}
        )


def has_prediction(date: str, symbol: str) -> bool:
    return any(r["Date"] == date and r["Symbol"] == symbol for r in read_rows())


def load_universe(path: Optional[Path] = None) -> List[str]:
    path = path or (Path(__file__).resolve().parent / "universe.txt")
    out: List[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            out.append(line.upper())
    return out


# --------------------------------------------------------------------------
# Market data (yfinance — already a project dependency)
# --------------------------------------------------------------------------

def _history(symbol: str, start: str, end: str):
    import yfinance as yf

    df = yf.Ticker(symbol).history(start=start, end=end, auto_adjust=True)
    return df


def close_on_or_before(symbol: str, date: str) -> Optional[float]:
    """Adjusted close on `date`, or the most recent trading day before it."""
    d = datetime.strptime(date, "%Y-%m-%d")
    df = _history(symbol, (d - timedelta(days=10)).strftime("%Y-%m-%d"),
                  (d + timedelta(days=1)).strftime("%Y-%m-%d"))
    if df is None or df.empty:
        return None
    return float(df["Close"].iloc[-1])


def close_on_or_after(symbol: str, date: str) -> Optional[float]:
    """Adjusted close on `date`, or the first trading day after it.

    Returns None if no bar exists yet (window hasn't matured / no data).
    """
    d = datetime.strptime(date, "%Y-%m-%d")
    df = _history(symbol, date, (d + timedelta(days=10)).strftime("%Y-%m-%d"))
    if df is None or df.empty:
        return None
    return float(df["Close"].iloc[0])


def horizon_date(date: str, days: int) -> str:
    return (datetime.strptime(date, "%Y-%m-%d") + timedelta(days=days)).strftime("%Y-%m-%d")
