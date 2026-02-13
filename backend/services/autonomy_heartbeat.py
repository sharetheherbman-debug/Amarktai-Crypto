"""
Autonomy Heartbeat Registry
Tracks last_ok and last_error timestamps for autonomy subsystems.
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
]


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


heartbeat_registry = AutonomyHeartbeatRegistry()
