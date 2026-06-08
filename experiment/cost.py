"""Token + cost accounting for experiment runs.

Token counts come straight from each provider's `usage_metadata` and are
accurate. Dollar figures are ESTIMATES from an editable price table — model
prices change often and vary by provider/tier, so treat $ as a guide and
reconcile against your provider's billing dashboard.

Override prices WITHOUT editing code by creating experiment/prices.json, e.g.:

    {
      "gpt-5.4-mini": {"input": 0.25, "output": 2.00},
      "gpt-5.5":      {"input": 1.25, "output": 10.00}
    }

Values are USD per 1,000,000 tokens. Keys are matched as case-insensitive
substrings of the model name the provider reports.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional, Tuple

_PRICES_PATH = Path(__file__).resolve().parent / "prices.json"

# USD per 1,000,000 tokens. PLACEHOLDERS for the project's default OpenAI
# models — VERIFY against current pricing for your account, or override via
# experiment/prices.json. Unknown models still get accurate token counts;
# their cost is reported as unpriced.
DEFAULT_PRICES: Dict[str, Dict[str, float]] = {
    "gpt-5.5":      {"input": 1.25, "output": 10.00},
    "gpt-5.4-mini": {"input": 0.25, "output": 2.00},
    "gpt-5.4":      {"input": 1.25, "output": 10.00},
}


def load_prices() -> Dict[str, Dict[str, float]]:
    prices = {k.lower(): v for k, v in DEFAULT_PRICES.items()}
    if _PRICES_PATH.exists():
        try:
            override = json.loads(_PRICES_PATH.read_text(encoding="utf-8"))
            prices.update({k.lower(): v for k, v in override.items()})
        except (json.JSONDecodeError, OSError):
            pass  # bad override file shouldn't crash a run
    return prices


def _price_for(model: str, prices: Dict[str, Dict[str, float]]) -> Optional[Dict[str, float]]:
    m = (model or "").lower()
    # Longest key wins so "gpt-5.4-mini" beats "gpt-5.4".
    best = None
    for key, val in prices.items():
        if key in m and (best is None or len(key) > len(best[0])):
            best = (key, val)
    return best[1] if best else None


def summarize(usage_metadata: Dict[str, dict]) -> Dict[str, object]:
    """Collapse a get_usage_metadata_callback() result into flat totals.

    `usage_metadata` is keyed by model name, each value carrying
    input_tokens / output_tokens / total_tokens. Returns input/output/total
    token sums, an estimated USD cost (None if no model was priced), and the
    list of models we couldn't price.
    """
    prices = load_prices()
    in_tok = out_tok = 0
    cost = 0.0
    priced_any = False
    unpriced = []

    for model, u in (usage_metadata or {}).items():
        ui = int(u.get("input_tokens", 0) or 0)
        uo = int(u.get("output_tokens", 0) or 0)
        in_tok += ui
        out_tok += uo
        p = _price_for(model, prices)
        if p:
            priced_any = True
            cost += ui / 1_000_000 * p["input"] + uo / 1_000_000 * p["output"]
        elif ui or uo:
            unpriced.append(model)

    return {
        "input": in_tok,
        "output": out_tok,
        "total": in_tok + out_tok,
        "cost": round(cost, 4) if priced_any else None,
        "unpriced": unpriced,
    }


def fmt(summary: Dict[str, object]) -> str:
    cost = summary["cost"]
    cost_str = f"${cost:.4f}" if cost is not None else "$? (price unset)"
    tail = ""
    if summary["unpriced"]:
        tail = f"  [unpriced: {', '.join(sorted(set(summary['unpriced'])))}]"
    return (f"{summary['input']:,} in / {summary['output']:,} out tok  "
            f"~{cost_str}{tail}")
