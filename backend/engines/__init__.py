"""
Engines package for Amarktai Network.
Exposes engine sub-modules used throughout the system.
"""

# Re-export regime detection under the 'market_regime' name that the system uses
from engines import regime_detector as market_regime  # noqa: F401

# Lazy-import paper_trading engine from the backend root module
import sys as _sys
import os as _os
import importlib as _importlib
import types as _types

def _get_paper_trading():
    """Return the paper_trading module, importing it from the project root if needed."""
    if "engines.paper_trading" in _sys.modules:
        return _sys.modules["engines.paper_trading"]

    # Try to import backend.paper_trading_engine from the project root
    _backend_dir = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
    if _backend_dir not in _sys.path:
        _sys.path.insert(0, _backend_dir)

    try:
        _mod = _importlib.import_module("paper_trading_engine")
        # Register it as engines.paper_trading for future imports
        _sys.modules["engines.paper_trading"] = _mod
        return _mod
    except Exception:
        # Fallback: return a minimal stub so imports never fail at collection time
        _stub = _types.ModuleType("engines.paper_trading")
        _stub.__doc__ = "Paper trading engine stub (real module unavailable at import time)"
        _sys.modules["engines.paper_trading"] = _stub
        return _stub


# Make 'paper_trading' available as an attribute of this package
paper_trading = _get_paper_trading()
