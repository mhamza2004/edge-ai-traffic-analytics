"""
Vehicle speed estimation.

Uses the same method real "average speed check" camera systems use (e.g. UK
SPECS cameras): two tripwire lines a KNOWN real-world distance apart. A
vehicle's speed = that known distance / the real time it took to cross from
line A to line B.

This is deliberately NOT "guess a pixels-per-meter ratio for the whole frame
and multiply every frame's movement by it" -- on a camera with any real
perspective (like ours), a single frame-wide ratio is only accurate near
wherever it was calibrated and drifts everywhere else. Measuring real time
between two known, specific points sidesteps that: it only needs the
distance between those two lines to be correct, not the whole frame's
geometry.

Trade-off: a vehicle only gets a speed reading once it has crossed BOTH
lines of a zone, and only for vehicles whose path actually passes through
the zone -- it's not a per-frame instantaneous speed. That's an accurate
reflection of what this method can honestly measure with one camera.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .detector import Detection
from .geometry import segments_intersect

Point = Tuple[float, float]


@dataclass
class SpeedZone:
    name: str
    line_a: Tuple[Point, Point]
    line_b: Tuple[Point, Point]
    distance_m: float


@dataclass
class _TrackCrossings:
    last_center: Optional[Point] = None
    a_crossed_at: Optional[float] = None
    b_crossed_at: Optional[float] = None
    speed_kmh: Optional[float] = None


class SpeedEstimator:
    def __init__(self, cfg: dict):
        self.enabled = cfg.get("enabled", False)
        self.zones: List[SpeedZone] = [
            SpeedZone(
                name=z["name"],
                line_a=(tuple(z["line_a"]["p1"]), tuple(z["line_a"]["p2"])),
                line_b=(tuple(z["line_b"]["p1"]), tuple(z["line_b"]["p2"])),
                distance_m=float(z["distance_m"]),
            )
            for z in cfg.get("zones", [])
        ]
        self.max_reasonable_kmh = cfg.get("max_reasonable_kmh", 180)
        # per (zone_name, track_id) -> _TrackCrossings
        self._tracks: Dict[Tuple[str, int], _TrackCrossings] = {}
        # last known speed per track_id, regardless of zone -- what evidence
        # snapshots/violation events look up when a violation fires
        self._last_known_speed: Dict[int, float] = {}

    def update(self, detections: List[Detection]) -> None:
        if not self.enabled or not self.zones:
            return
        now = time.time()
        for det in detections:
            center = det.center
            for zone in self.zones:
                key = (zone.name, det.track_id)
                st = self._tracks.setdefault(key, _TrackCrossings())

                if st.last_center is not None:
                    if st.a_crossed_at is None and segments_intersect(st.last_center, center, *zone.line_a):
                        st.a_crossed_at = now
                    if st.b_crossed_at is None and segments_intersect(st.last_center, center, *zone.line_b):
                        st.b_crossed_at = now

                    if st.a_crossed_at is not None and st.b_crossed_at is not None and st.speed_kmh is None:
                        elapsed = abs(st.b_crossed_at - st.a_crossed_at)
                        if elapsed > 0.05:  # ignore near-zero elapsed times (noise / same-frame double count)
                            speed = (zone.distance_m / elapsed) * 3.6
                            if 0 < speed <= self.max_reasonable_kmh:
                                st.speed_kmh = speed
                                self._last_known_speed[det.track_id] = speed

                st.last_center = center

    def speed_for(self, track_id: int) -> Optional[float]:
        """Last known estimated speed (km/h) for this track, if any measurement completed."""
        return self._last_known_speed.get(track_id)

    def forget(self, track_id: int):
        self._last_known_speed.pop(track_id, None)
        keys_to_drop = [k for k in self._tracks if k[1] == track_id]
        for k in keys_to_drop:
            del self._tracks[k]
