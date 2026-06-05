"""Quantitative-evaluation harness for TradingAgents.

Run it like an experiment, not a trading account:
  run.py    -> generate + archive predictions over a fixed universe (paper only)
  score.py  -> fill forward returns vs SPY once windows mature
  review.py -> hit-rate, excess vs SPY, calibration slices (with stat guardrails)

See experiment/README.md.
"""
