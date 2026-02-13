"""
Autonomy State Flags
Tracks manual pause/resume toggles for subsystems.
"""

import threading
from typing import Dict


class AutonomyState:
    def __init__(self):
        self._lock = threading.Lock()
        self._paused: Dict[str, bool] = {}

    def is_paused(self, subsystem: str) -> bool:
        with self._lock:
            return self._paused.get(subsystem, False)

    def set_paused(self, subsystem: str, paused: bool) -> None:
        with self._lock:
            self._paused[subsystem] = paused

    def snapshot(self) -> Dict[str, bool]:
        with self._lock:
            return dict(self._paused)


autonomy_state = AutonomyState()
