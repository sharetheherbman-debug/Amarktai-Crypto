"""
Self-Healing System – canonical re-export shim.

All self-healing logic lives in engines/self_healing.py.
This module re-exports the canonical singleton so that legacy
imports (``from self_healing import self_healing``) continue to
work without maintaining a second, divergent instance.
"""

# Re-export the canonical singleton.  Any module that imports
# ``self_healing`` or ``self_healing_monitor`` from here will
# receive the same instance that services/lifecycle.py starts.
from engines.self_healing import self_healing, self_healing as self_healing_monitor  # noqa: F401

# Keep SelfHealingSystem importable for tests / static analysis.
from engines.self_healing import SelfHealingSystem  # noqa: F401
