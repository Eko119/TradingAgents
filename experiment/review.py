"""Weekly review: summarise scored predictions.

Headline question (per the experiment): do the DIRECTIONAL calls beat the
market, and is the sample big enough to believe it?

Reports, for each horizon:
  * n scored directional calls (Holds excluded)
  * hit-rate (CallCorrect) with a binomial test vs the 50% coin-flip null
  * mean / median excess return vs SPY
  * a rough "effective sample size" warning based on how concentrated the
    calls are in a single day (correlated bets), and
  * breakdowns by rating and by sentiment-confidence bucket — labelled as
    HYPOTHESIS-GENERATING ONLY, because slicing a ~100-row sample many ways
    manufactures patterns that won't survive a fresh batch.

Pure stdlib + the project's existing deps. No new requirements.

Usage:
    python -m experiment.review
"""

from __future__ import annotations

import argparse
import math
from collections import Counter, defaultdict
from typing import List

from experiment import store

HORIZONS = ("7d", "30d")


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _binom_two_sided_p(k: int, n: int, p: float = 0.5) -> float:
    """Exact two-sided binomial p-value vs p=0.5 (small n, no scipy needed)."""
    if n == 0:
        return 1.0
    from math import comb
    probs = [comb(n, i) * p**i * (1 - p)**(n - i) for i in range(n + 1)]
    obs = probs[k]
    return min(1.0, sum(pr for pr in probs if pr <= obs + 1e-12))


def _mean(xs: List[float]):
    return sum(xs) / len(xs) if xs else None


def _median(xs: List[float]):
    if not xs:
        return None
    s = sorted(xs)
    m = len(s) // 2
    return s[m] if len(s) % 2 else (s[m - 1] + s[m]) / 2


def _fmt_pct(x):
    return "—" if x is None else f"{x*100:+.2f}%"


def review() -> None:
    rows = [r for r in store.read_rows() if r.get("Status") == "scored"]
    total = len(store.read_rows())
    print("=" * 64)
    print(f"TradingAgents experiment review — {len(rows)} scored / {total} total predictions")
    print("=" * 64)
    if not rows:
        print("No scored predictions yet. Run `python -m experiment.score` once a "
              "7d/30d window has elapsed.")
        return

    for tag in HORIZONS:
        calls = [r for r in rows if r.get(f"CallCorrect_{tag}") in ("Y", "N")]
        excess = [(_f(r.get(f"Excess_{tag}"))) for r in rows]
        excess = [e for e in excess if e is not None]
        n = len(calls)
        wins = sum(1 for r in calls if r[f"CallCorrect_{tag}"] == "Y")

        print(f"\n── {tag} horizon ──")
        if n == 0:
            print("  no directional calls scored yet")
            continue
        hit = wins / n
        p = _binom_two_sided_p(wins, n)
        print(f"  directional calls : {n} (Holds excluded)")
        print(f"  hit-rate          : {hit*100:.1f}%  ({wins}/{n})   "
              f"binomial p vs 50% = {p:.3f}{'  *' if p < 0.05 else ''}")
        print(f"  mean excess vs SPY: {_fmt_pct(_mean(excess))}   "
              f"median: {_fmt_pct(_median(excess))}")

        # Effective-sample warning: how clustered are calls within single days?
        per_day = Counter(r["Date"] for r in calls)
        biggest_day = max(per_day.values())
        if biggest_day / n > 0.4:
            print(f"  ⚠ {biggest_day}/{n} calls come from one date — highly correlated; "
                  f"effective sample << {n}. Treat significance with suspicion.")

    # ---- hypothesis-generating slices (clearly fenced) ----
    print("\n" + "-" * 64)
    print("SLICES BELOW ARE HYPOTHESIS-GENERATING ONLY (multiple-comparisons /")
    print("p-hacking risk at small n). Any pattern must survive a FRESH batch.")
    print("-" * 64)

    for tag in HORIZONS:
        print(f"\n[{tag}] hit-rate by rating:")
        by_rating = defaultdict(lambda: [0, 0])
        for r in rows:
            cc = r.get(f"CallCorrect_{tag}")
            if cc in ("Y", "N"):
                by_rating[r["Rating"]][0] += cc == "Y"
                by_rating[r["Rating"]][1] += 1
        for rating, (w, c) in sorted(by_rating.items()):
            print(f"    {rating:<12} {w}/{c}  ({(w/c*100) if c else 0:.0f}%)")

        print(f"[{tag}] hit-rate by sentiment confidence (proxy, not trade confidence):")
        by_conf = defaultdict(lambda: [0, 0])
        for r in rows:
            cc = r.get(f"CallCorrect_{tag}")
            if cc in ("Y", "N"):
                key = r.get("SentimentConfidence") or "n/a"
                by_conf[key][0] += cc == "Y"
                by_conf[key][1] += 1
        for conf, (w, c) in sorted(by_conf.items()):
            print(f"    {conf:<8} {w}/{c}  ({(w/c*100) if c else 0:.0f}%)")

    print("\nMilestone check: you're looking for hit-rate > 50% with binomial")
    print("p < 0.05 AND positive mean excess vs SPY, on independent calls.")


def main(argv=None) -> int:
    argparse.ArgumentParser(description="Summarise scored predictions.").parse_args(argv)
    review()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
