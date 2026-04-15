"""
Amarktai Crypto — Research & Strategy Validation Package
=========================================================
This package is a SIDECAR to the live trading app.
It must NEVER be imported by the live engine (paper_trading_engine.py,
trading_scheduler.py, etc.).

Workflow (A → B → C):
  A. Research ideas here (vectorbt_runner.py, notebook)
  B. Validate in Freqtrade (../validation/freqtrade/)
  C. Promote a validated config to the live engine via promote_strategy.py

Only strategies in stage="validated" or stage="active" should be used
in production. The live engine reads from strategies/active.json.
"""
