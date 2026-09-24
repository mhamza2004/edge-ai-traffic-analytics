"""
Multi-lane directional flow counter.

Extends the classic "line-crossing tripwire" pattern (seen in the
sopheakchan reference repo) with:
  - lane assignment via polygon containment, so counts are split per lane
  - direction (inbound / outbound) inferred from which lane the vehicle is in
  - de-duplication per (track_id, line) so a vehicle is never double counted
  - a small time-windowed "vehicles currently present" gauge for congestion
"""
from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .detector import Detection
from .geometry import point_in_polygon, segments_intersect

Point = Tuple[float, float]


@dataclass
class CountingLine:
    name: str
    p1: Point
    p2: Point


@dataclass
class Lane:
    name: str
    direction: str
    polygon: List[Point]
    allowed_vector: Tuple[float, float] = (0.0, 1.0)


@dataclass
class _TrackState:
    last_center: Optional[Point] = None
    lane_name: Optional[str] = None
    counted_lines: set = field(default_factory=set)
    last_seen: float = field(default_factory=time.time)
    history: List[Point] = field(default_factory=list)  # recent centers for direction/violation logic


class FlowCounter:
    def __init__(self, lanes_cfg: List[dict], lines_cfg: List[dict], present_timeout_s: float = 2.0):
        self.lanes = [
            Lane(
                name=l["name"],
                direction=l["direction"],
                polygon=[tuple(pt) for pt in l["polygon"]],
                allowed_vector=tuple(l.get("allowed_vector", (0, 1))),
            )
            for l in lanes_cfg
        ]
        self.lines = [CountingLine(name=c["name"], p1=tuple(c["p1"]), p2=tuple(c["p2"])) for c in lines_cfg]
        self.present_timeout_s = present_timeout_s

        self.tracks: Dict[int, _TrackState] = {}

        # counts[lane_name][cls_name] = int
        self.counts: Dict[str, Dict[str, int]] = {l.name: defaultdict(int) for l in self.lanes}
        self.direction_totals: Dict[str, int] = defaultdict(int)  # inbound / outbound
        self.class_totals: Dict[str, int] = defaultdict(int)
        self.total_count = 0

    def _lane_for_point(self, pt: Point) -> Optional[Lane]:
        for lane in self.lanes:
            if point_in_polygon(pt, lane.polygon):
                return lane
        return None

    def update(self, detections: List[Detection]) -> List[dict]:
        """Feed one frame's detections in. Returns list of newly counted events."""
        now = time.time()
        seen_ids = set()
        new_events: List[dict] = []

        for det in detections:
            seen_ids.add(det.track_id)
            state = self.tracks.setdefault(det.track_id, _TrackState())
            center = det.center

            lane = self._lane_for_point(center)
            if lane is not None:
                state.lane_name = lane.name

            if state.last_center is not None:
                for line in self.lines:
                    key = line.name
                    if key in state.counted_lines:
                        continue
                    if segments_intersect(state.last_center, center, line.p1, line.p2):
                        state.counted_lines.add(key)
                        lane_name = state.lane_name or "Unassigned"
                        lane_obj = next((l for l in self.lanes if l.name == lane_name), None)
                        direction = lane_obj.direction if lane_obj else "unknown"

                        self.counts.setdefault(lane_name, defaultdict(int))
                        self.counts[lane_name][det.cls_name] += 1
                        self.direction_totals[direction] += 1
                        self.class_totals[det.cls_name] += 1
                        self.total_count += 1

                        event = {
                            "type": "count",
                            "track_id": det.track_id,
                            "lane": lane_name,
                            "direction": direction,
                            "vehicle_class": det.cls_name,
                            "line": line.name,
                            "timestamp": now,
                        }
                        new_events.append(event)

            state.history.append(center)
            if len(state.history) > 30:
                state.history.pop(0)
            state.last_center = center
            state.last_seen = now

        # drop stale tracks (helps memory + the "currently present" gauge)
        stale = [tid for tid, st in self.tracks.items() if now - st.last_seen > self.present_timeout_s and tid not in seen_ids]
        for tid in stale:
            del self.tracks[tid]

        return new_events

    def currently_present(self) -> int:
        return len(self.tracks)

    def snapshot(self) -> dict:
        return {
            "total_count": self.total_count,
            "by_lane": {lane: dict(cls_counts) for lane, cls_counts in self.counts.items()},
            "by_direction": dict(self.direction_totals),
            "by_class": dict(self.class_totals),
            "currently_present": self.currently_present(),
        }
