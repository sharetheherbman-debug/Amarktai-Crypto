"""
Autonomy Heartbeat Registry
Tracks last_ok and last_error timestamps for autonomy subsystems.
Provides watchdog-style stale detection for background task health.
"""

from datetime import datetime, timezone
from typing import Dict, Optional
import logging
import threading

logger = logging.getLogger(__name__)


DEFAULT_SUBSYSTEMS = [
    "autopilot",
    "trading_scheduler",
    "realtime",
    "self_heal",
    "bodyguard",
    "learning_loop",
    "daily_loss_reset",
]

# Maximum seconds before a subsystem is considered stale/dead
STALE_THRESHOLDS = {
    "trading_scheduler": 60,     # Should heartbeat every ~10s
    "daily_loss_reset": 86400,   # Daily job, expect once per 24h
    "autopilot": 120,
    "realtime": 120,
    "self_heal": 300,
    "bodyguard": 300,
    "learning_loop": 600,
}

DEFAULT_STALE_THRESHOLD = 300  # 5 minutes


class AutonomyHeartbeatRegistry:
    def __init__(self):
        self._lock = threading.Lock()
        self._state: Dict[str, Dict[str, Optional[str]]] = {}
        for subsystem in DEFAULT_SUBSYSTEMS:
            self._state[subsystem] = {
                "last_ok_at": None,
                "last_error_at": None,
                "last_error_message": None,
            }

    def _ensure(self, subsystem: str) -> None:
        if subsystem not in self._state:
            self._state[subsystem] = {
                "last_ok_at": None,
                "last_error_at": None,
                "last_error_message": None,
            }

    def mark_ok(self, subsystem: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._ensure(subsystem)
            self._state[subsystem]["last_ok_at"] = now
        logger.debug("Heartbeat ok: %s", subsystem)

    def mark_error(self, subsystem: str, message: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._ensure(subsystem)
            self._state[subsystem]["last_error_at"] = now
            self._state[subsystem]["last_error_message"] = message
        logger.warning("Heartbeat error for %s: %s", subsystem, message)

    def snapshot(self) -> Dict[str, Dict[str, Optional[str]]]:
        with self._lock:
            return {key: value.copy() for key, value in self._state.items()}

    def check_stale(self) -> Dict[str, dict]:
        """Return watchdog status for all subsystems.

        For each subsystem returns:
        - alive: bool (True if last_ok_at is within threshold)
        - stale_seconds: float | None (seconds since last heartbeat)
        - threshold: int (expected max seconds between heartbeats)
        """
        now = datetime.now(timezone.utc)
        result = {}
        with self._lock:
            for subsystem, state in self._state.items():
                threshold = STALE_THRESHOLDS.get(subsystem, DEFAULT_STALE_THRESHOLD)
                last_ok = state.get("last_ok_at")
                if last_ok:
                    try:
                        last_ok_dt = datetime.fromisoformat(last_ok.replace("Z", "+00:00"))
                        stale_seconds = (now - last_ok_dt).total_seconds()
                    except (ValueError, TypeError):
                        stale_seconds = None
                else:
                    stale_seconds = None

                alive = stale_seconds is not None and stale_seconds <= threshold
                result[subsystem] = {
                    "alive": alive,
                    "stale_seconds": round(stale_seconds, 1) if stale_seconds is not None else None,
                    "threshold": threshold,
                    "last_ok_at": last_ok,
                    "last_error_at": state.get("last_error_at"),
                    "last_error_message": state.get("last_error_message"),
                }
        return result


heartbeat_registry = AutonomyHeartbeatRegistry()
