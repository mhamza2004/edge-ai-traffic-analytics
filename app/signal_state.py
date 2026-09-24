"""
Traffic signal state source.

Red-light violation detection needs to know the current signal phase.
Three modes are supported:

  - "simulator": cycles GREEN -> YELLOW -> RED on a timer. Useful for demos
     and for sites where the signal isn't yet wired into the system.
  - "manual": phase is set programmatically (e.g. from a small admin
     endpoint) -- call `set_phase()`.
  - "mqtt": phase is driven by messages arriving on an MQTT topic (e.g. from
     the signal controller's own PLC/relay board publishing its state).
     Call `set_phase()` from your MQTT on_message callback.

All three expose the same `.phase` property so ViolationManager doesn't
need to care which one is active.
"""
from __future__ import annotations

import time
from enum import Enum


class SignalPhase(str, Enum):
    GREEN = "GREEN"
    YELLOW = "YELLOW"
    RED = "RED"


class SignalState:
    def __init__(self, mode: str = "simulator", sim_cfg: dict | None = None):
        self.mode = mode
        self.sim_cfg = sim_cfg or {"green_seconds": 12, "yellow_seconds": 3, "red_seconds": 8}
        self._phase = SignalPhase.GREEN
        self._phase_started_at = time.time()

    @property
    def phase(self) -> SignalPhase:
        if self.mode == "simulator":
            self._tick_simulator()
        return self._phase

    def _tick_simulator(self):
        elapsed = time.time() - self._phase_started_at
        durations = {
            SignalPhase.GREEN: self.sim_cfg.get("green_seconds", 12),
            SignalPhase.YELLOW: self.sim_cfg.get("yellow_seconds", 3),
            SignalPhase.RED: self.sim_cfg.get("red_seconds", 8),
        }
        if elapsed >= durations[self._phase]:
            order = [SignalPhase.GREEN, SignalPhase.YELLOW, SignalPhase.RED]
            self._phase = order[(order.index(self._phase) + 1) % len(order)]
            self._phase_started_at = time.time()

    def set_phase(self, phase: SignalPhase | str):
        self._phase = SignalPhase(phase)
        self._phase_started_at = time.time()

    def is_red(self) -> bool:
        return self.phase == SignalPhase.RED
