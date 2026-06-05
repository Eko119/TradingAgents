"""Step 6: fill forward-return columns for predictions whose holding window
has matured, benchmarked against SPY.

For each pending row it computes, at the 7-day and 30-day calendar horizon:
  Ret      = symbol close at horizon / AsOfPrice - 1
  SPY_Ret  = SPY close at horizon   / SPY AsOf  - 1
  Excess   = Ret - SPY_Ret                       (alpha vs market)
  BeatSPY  = Excess > 0
  CallCorrect = the DIRECTIONAL call paid off vs the market:
               long (Buy/Overweight) right when Excess > 0,
               short (Sell/Underweight) right when Excess < 0,
               Hold -> blank (no directional bet).

A row is only marked Status=scored once BOTH horizons have data. Rows whose
30-day window hasn't elapsed yet are left pending and topped up on a later run.

Usage:
    python -m experiment.score              # score everything mature
    python -m experiment.score --asof 2026-07-10   # pretend "today" is this date
"""

from __future__ import annotations

import argparse
from datetime import date as date_cls

from experiment import store

HORIZONS = (("7d", 7), ("30d", 30))


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _spy_cache():
    cache = {}

    def spy_close(date: str):
        if date not in cache:
            cache[date] = store.close_on_or_after(store.BENCHMARK, date)
        return cache[date]

    return spy_close


def score(asof: str) -> dict:
    rows = store.read_rows()
    spy_close = _spy_cache()
    stats = {"scored": 0, "updated": 0, "still_pending": 0, "skipped": 0}

    for row in rows:
        if row.get("Status") not in ("pending", ""):
            stats["skipped"] += 1
            continue
        sym = row["Symbol"]
        entry = _f(row.get("AsOfPrice"))
        if entry is None:
            # Backfill the entry price if the original run couldn't get it.
            entry = store.close_on_or_before(sym, row["Date"])
            row["AsOfPrice"] = "" if entry is None else round(entry, 4)
        spy_entry = spy_close(row["Date"])
        direction = _f(row.get("Direction")) or 0

        all_done = True
        for tag, days in HORIZONS:
            if row.get(f"Ret_{tag}") not in (None, ""):
                continue  # already filled
            h_date = store.horizon_date(row["Date"], days)
            if h_date > asof:  # window hasn't elapsed relative to "now"
                all_done = False
                continue
            px = store.close_on_or_after(sym, h_date)
            spy_px = spy_close(h_date)
            if px is None or spy_px is None or entry in (None, 0) or spy_entry in (None, 0):
                all_done = False
                continue

            ret = px / entry - 1.0
            spy_ret = spy_px / spy_entry - 1.0
            excess = ret - spy_ret
            row[f"Px_{tag}"] = round(px, 4)
            row[f"Ret_{tag}"] = round(ret, 6)
            row[f"SPY_Ret_{tag}"] = round(spy_ret, 6)
            row[f"Excess_{tag}"] = round(excess, 6)
            row[f"BeatSPY_{tag}"] = "Y" if excess > 0 else "N"
            if direction == 0:
                row[f"CallCorrect_{tag}"] = ""  # Hold: no directional bet
            else:
                row[f"CallCorrect_{tag}"] = "Y" if (excess * direction) > 0 else "N"
            stats["updated"] += 1

        if all_done and row.get("Ret_30d") not in (None, ""):
            row["Status"] = "scored"
            stats["scored"] += 1
        else:
            stats["still_pending"] += 1

    store.write_rows(rows)
    return stats


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Fill forward returns vs SPY for matured predictions.")
    p.add_argument("--asof", default=date_cls.today().isoformat(),
                   help="Treat this date as 'now' when deciding which windows have matured.")
    args = p.parse_args(argv)
    s = score(args.asof)
    print(f"scored={s['scored']}  cells_updated={s['updated']}  "
          f"still_pending={s['still_pending']}  already_scored={s['skipped']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
