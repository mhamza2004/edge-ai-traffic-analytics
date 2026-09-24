"""
Thread-safe shared state.

The CV pipeline runs in its own background thread (OpenCV capture loop);
the FastAPI app runs the asyncio event loop. This small object is the only
thing they share, guarded by a lock, so the dashboard/API can read the
latest frame + metrics without ever touching OpenCV objects directly.
"""
from __future__ import annotations

import threading
import time
from typing import List, Optional


class SharedState:
    def __init__(self, max_violation_log: int = 100):
        self._lock = threading.Lock()
        self._jpeg_frame: Optional[bytes] = None
        self._metrics: dict = {}
        self._violations: List[dict] = []
        self._max_violation_log = max_violation_log
        self._fps: float = 0.0
        self._started_at = time.time()
        self._frames_processed = 0

    def set_frame(self, jpeg_bytes: bytes):
        with self._lock:
            self._jpeg_frame = jpeg_bytes
            self._frames_processed += 1

    def get_frame(self) -> Optional[bytes]:
        with self._lock:
            return self._jpeg_frame

    def set_metrics(self, metrics: dict):
        with self._lock:
            self._metrics = metrics

    def get_metrics(self) -> dict:
        with self._lock:
            return dict(self._metrics)

    def add_violation(self, event: dict):
        with self._lock:
            self._violations.append(event)
            if len(self._violations) > self._max_violation_log:
                self._violations = self._violations[-self._max_violation_log:]

    def get_violations(self) -> List[dict]:
        with self._lock:
            return list(self._violations)

    def set_fps(self, fps: float):
        with self._lock:
            self._fps = fps

    def get_fps(self) -> float:
        with self._lock:
            return self._fps

    def uptime_seconds(self) -> float:
        return time.time() - self._started_at


shared_state = SharedState()
