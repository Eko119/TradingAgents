"""Pure extraction helpers: turn a TradingAgents final_state into flat,
loggable fields. No I/O, no network — easy to unit-test.

What TradingAgents actually emits (verified against tradingagents/agents/schemas.py):
  * Final decision (PortfolioDecision): a 5-tier `rating`
    (Buy/Overweight/Hold/Underweight/Sell), executive summary, thesis,
    optional price_target, optional time_horizon.
  * There is NO native per-decision confidence score. The only `confidence`
    field (low/medium/high) lives on the Sentiment Analyst report, alongside
    a 0-10 sentiment score. We surface those as the closest available
    "conviction" proxy and label them honestly — do not mistake sentiment
    confidence for the model's confidence in the trade.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

from tradingagents.agents.utils.rating import parse_rating

# Most-bullish -> most-bearish, mapped to a signed score for backtesting.
RATING_SCORE: Dict[str, int] = {
    "Buy": 2,
    "Overweight": 1,
    "Hold": 0,
    "Underweight": -1,
    "Sell": -2,
}

# A Buy/Overweight is a long (directional +1); Sell/Underweight a short (-1);
# Hold is no directional bet and is excluded from hit-rate stats.
def rating_direction(rating: str) -> int:
    s = RATING_SCORE.get(rating, 0)
    return (s > 0) - (s < 0)  # sign: +1 / 0 / -1


_SENT_BAND_RE = re.compile(r"Overall Sentiment:[\s*]*([A-Za-z][A-Za-z ]*?)[\s*]*\(Score:\s*([0-9.]+)", re.IGNORECASE)
_SENT_CONF_RE = re.compile(r"Confidence:[\s*]*(low|medium|high)", re.IGNORECASE)
_PRICE_TARGET_RE = re.compile(r"Price Target\*{0,2}\s*[:\-]\s*\$?([0-9][0-9,\.]*)", re.IGNORECASE)
_TIME_HORIZON_RE = re.compile(r"Time Horizon\*{0,2}\s*[:\-]\s*(.+)", re.IGNORECASE)
_EXEC_SUMMARY_RE = re.compile(r"Executive Summary\*{0,2}\s*[:\-]\s*(.+)", re.IGNORECASE)


def _first(pattern: re.Pattern, text: str, group: int = 1) -> Optional[str]:
    if not text:
        return None
    m = pattern.search(text)
    return m.group(group).strip() if m else None


def _to_float(s: Optional[str]) -> Optional[float]:
    if not s:
        return None
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return None


def extract_fields(final_state: Dict[str, Any], rating: str) -> Dict[str, Any]:
    """Flatten the pieces we log per prediction.

    `rating` is the already-parsed 5-tier string returned by
    TradingAgentsGraph.propagate() (its second return value).
    """
    decision_md = final_state.get("final_trade_decision", "") or ""
    sentiment_md = final_state.get("sentiment_report", "") or ""

    # Defensive: re-parse rating from the decision if the caller passed junk.
    if rating not in RATING_SCORE:
        rating = parse_rating(decision_md)

    sent_band = _first(_SENT_BAND_RE, sentiment_md, 1)
    sent_score = _to_float(_first(_SENT_BAND_RE, sentiment_md, 2))
    sent_conf = _first(_SENT_CONF_RE, sentiment_md)

    exec_summary = _first(_EXEC_SUMMARY_RE, decision_md)
    # Keep the thesis summary to a single line for the CSV.
    thesis = (exec_summary or decision_md.strip().splitlines()[0] if decision_md.strip() else "")
    thesis = re.sub(r"\s+", " ", thesis or "").strip()[:500]

    return {
        "Rating": rating,
        "Score": RATING_SCORE.get(rating, 0),
        "Direction": rating_direction(rating),
        "SentimentBand": sent_band or "",
        "SentimentScore": sent_score if sent_score is not None else "",
        "SentimentConfidence": (sent_conf or "").lower(),
        "PriceTarget": _to_float(_first(_PRICE_TARGET_RE, decision_md)) or "",
        "TimeHorizon": _first(_TIME_HORIZON_RE, decision_md) or "",
        "ThesisSummary": thesis,
    }
