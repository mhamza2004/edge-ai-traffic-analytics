"""
Automated traffic violation detection.

Three detectors, each looking at the same per-track history the FlowCounter
already maintains conceptually, but kept independent here so any one of them
can be enabled/disabled/tuned without touching the others:

  - WrongWayDetector        : movement direction vs. the lane's allowed_vector
  - RedLightViolationDetector: crossing a stop-line while SignalState.is_red()
  - IllegalLaneChangeDetector: lane assigned to a track flips too often
                                inside a designated "no lane change" zone

All three emit plain dict "violation events" with enough context (track id,
class, bbox, type, confidence-ish severity) for telemetry + evidence saving.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional, Tuple

from .detector import Detection
from .geometry import angle_between_deg, point_in_polygon, segments_intersect

Point = Tuple[float, float]


# --------------------------------------------------------------------------- #
# Wrong-way driving
# --------------------------------------------------------------------------- #
@dataclass
class _WrongWayTrack:
    history: Deque[Point] = field(default_factory=lambda: deque(maxlen=20))
    violating_streak: int = 0
    already_flagged: bool = False


class WrongWayDetector:
    def __init__(self, cfg: dict, lanes):
        self.enabled = cfg.get("enabled", True)
        self.min_track_history = cfg.get("min_track_history", 10)
        self.min_step_displacement_px = cfg.get("min_step_displacement_px", 3)
        self.min_valid_steps = cfg.get("min_valid_steps", 6)
        self.consistency_ratio = cfg.get("consistency_ratio", 0.75)
        self.angle_threshold_deg = cfg.get("angle_threshold_deg", 140)
        self.confirm_frames = cfg.get("confirm_frames", 8)
        # Small/far-away vehicles (near a vanishing point) move only a few pixels per frame --
        # detection-box jitter at that scale can look like "opposite direction" motion even when
        # the vehicle is driving normally. Skip the check entirely below this box height.
        self.min_bbox_height_px = cfg.get("min_bbox_height_px", 18)
        self.max_step_displacement_px = cfg.get("max_step_displacement_px", 25)
        self.lanes = lanes  # list[Lane] from flow_counter, for allowed_vector lookup
        self._tracks: Dict[int, _WrongWayTrack] = {}

    def _lane_for_point(self, pt: Point):
        for lane in self.lanes:
            if point_in_polygon(pt, lane.polygon):
                return lane
        return None

    def update(self, det: Detection) -> Optional[dict]:
        if not self.enabled:
            return None

        bbox_height = det.y2 - det.y1
        if bbox_height < self.min_bbox_height_px:
            return None

        st = self._tracks.setdefault(det.track_id, _WrongWayTrack())
        st.history.append(det.center)

        if len(st.history) < self.min_track_history or st.already_flagged:
            return None

        lane = self._lane_for_point(det.center)
        if lane is None:
            return None

        # Consistency-based direction check: look at EVERY consecutive frame-to-frame step
        # (not just the net start->end displacement), throw out steps too small to be real
        # motion, and require most of the remaining steps to agree the vehicle is travelling
        # opposite to the lane's allowed direction. This is far more resistant to a single
        # noisy detection jump than a "one net vector" check.
        #
        # It is NOT resistant to a tracker ID-swap (ByteTrack occasionally re-associates a
        # track ID to a different nearby vehicle after an occlusion/crossing -- ID swaps are a
        # known hard problem in multi-object tracking, not specific to this codebase). A swap
        # shows up as one anomalously large frame-to-frame jump compared to the rest of the
        # track's own movement, so any step bigger than max_step_displacement_px is treated as
        # a probable identity break: history before that point is discarded rather than
        # blended with the (likely different) vehicle's motion afterward.
        pts = list(st.history)
        break_idx = 0
        for i in range(1, len(pts)):
            dx = pts[i][0] - pts[i - 1][0]
            dy = pts[i][1] - pts[i - 1][1]
            if (dx * dx + dy * dy) ** 0.5 > self.max_step_displacement_px:
                break_idx = i  # discard everything up to and including the jump
        pts = pts[break_idx:]

        valid_steps = 0
        opposing_steps = 0
        for i in range(1, len(pts)):
            dx = pts[i][0] - pts[i - 1][0]
            dy = pts[i][1] - pts[i - 1][1]
            if (dx * dx + dy * dy) ** 0.5 < self.min_step_displacement_px:
                continue
            valid_steps += 1
            if angle_between_deg((dx, dy), lane.allowed_vector) >= self.angle_threshold_deg:
                opposing_steps += 1

        if valid_steps < self.min_valid_steps:
            st.violating_streak = 0
            return None

        ratio = opposing_steps / valid_steps
        if ratio >= self.consistency_ratio:
            st.violating_streak += 1
        else:
            st.violating_streak = 0

        if st.violating_streak >= self.confirm_frames:
            st.already_flagged = True
            # report using the net displacement angle purely for a human-readable summary
            start, end = pts[0], pts[-1]
            net_vec = (end[0] - start[0], end[1] - start[1])
            angle = angle_between_deg(net_vec, lane.allowed_vector)
            return {
                "type": "wrong_way",
                "track_id": det.track_id,
                "vehicle_class": det.cls_name,
                "lane": lane.name,
                "bbox": det.bbox,
                "angle_deg": round(angle, 1),
                "consistency": round(ratio, 2),
                "timestamp": time.time(),
                "severity": "high",
            }
        return None

    def forget(self, track_id: int):
        self._tracks.pop(track_id, None)


# --------------------------------------------------------------------------- #
# Red-light jumping
# --------------------------------------------------------------------------- #
class RedLightViolationDetector:
    def __init__(self, cfg: dict, signal_state):
        self.enabled = cfg.get("enabled", True)
        self.stop_line_p1 = tuple(cfg["stop_line"]["p1"])
        self.stop_line_p2 = tuple(cfg["stop_line"]["p2"])
        self.signal_state = signal_state
        self._last_center: Dict[int, Point] = {}
        self._already_flagged: set = set()

    def update(self, det: Detection) -> Optional[dict]:
        if not self.enabled:
            return None
        center = det.center
        prev = self._last_center.get(det.track_id)
        self._last_center[det.track_id] = center

        if prev is None or det.track_id in self._already_flagged:
            return None

        crossed = segments_intersect(prev, center, self.stop_line_p1, self.stop_line_p2)
        if crossed and self.signal_state.is_red():
            self._already_flagged.add(det.track_id)
            return {
                "type": "red_light",
                "track_id": det.track_id,
                "vehicle_class": det.cls_name,
                "bbox": det.bbox,
                "signal_phase": self.signal_state.phase.value,
                "timestamp": time.time(),
                "severity": "critical",
            }
        return None

    def forget(self, track_id: int):
        self._last_center.pop(track_id, None)
        self._already_flagged.discard(track_id)


# --------------------------------------------------------------------------- #
# Illegal lane cut-in / lane change inside a restricted zone
# --------------------------------------------------------------------------- #
@dataclass
class _LaneChangeTrack:
    lane_history: Deque[Tuple[float, int]] = field(default_factory=lambda: deque(maxlen=20))
    already_flagged: bool = False


class IllegalLaneCutInDetector:
    def __init__(self, cfg: dict, sub_lanes: list):
        self.enabled = cfg.get("enabled", True)
        self.zone_polygon = [tuple(p) for p in cfg.get("zone_polygon", [])]
        self.max_switches_allowed = cfg.get("max_switches_allowed", 1)
        self.window_seconds = cfg.get("window_seconds", 4)
        # Uses fine-grained individual-lane polygons (e.g. "Lane-1".."Lane-4" within one
        # carriageway), NOT the coarse Near/Far-Carriageway direction lanes used for counting
        # and wrong-way detection -- a "lane change" is meaningless at the carriageway level.
        self.sub_lanes = sub_lanes
        self._tracks: Dict[int, _LaneChangeTrack] = {}

    def _sub_lane_index_for(self, pt: Point) -> Optional[int]:
        for lane in self.sub_lanes:
            if point_in_polygon(pt, lane["polygon"]):
                return lane["index"]
        return None

    def update(self, det: Detection) -> Optional[dict]:
        if not self.enabled or not self.zone_polygon or not self.sub_lanes:
            return None
        center = det.center
        if not point_in_polygon(center, self.zone_polygon):
            return None

        idx = self._sub_lane_index_for(center)
        if idx is None:
            return None

        st = self._tracks.setdefault(det.track_id, _LaneChangeTrack())
        now = time.time()
        st.lane_history.append((now, idx))

        # keep only entries inside the rolling window
        while st.lane_history and now - st.lane_history[0][0] > self.window_seconds:
            st.lane_history.popleft()

        # Count only "erratic" transitions: a lane index moving the OPPOSITE direction from
        # the immediately preceding transition, or jumping by more than one lane in a single
        # step. A vehicle smoothly drifting Lane-1 -> Lane-2 -> Lane-3 in the same direction
        # the whole time is just normal perspective/lane-position drift as it recedes down the
        # road on a converging-perspective camera, NOT a lane change -- only a genuine
        # direction reversal or a multi-lane jump indicates the vehicle actually cut across.
        indices = [x[1] for x in st.lane_history]
        steps = [indices[i] - indices[i - 1] for i in range(1, len(indices)) if indices[i] != indices[i - 1]]
        erratic_switches = 0
        for i, step in enumerate(steps):
            if abs(step) > 1:
                erratic_switches += 1
            elif i > 0 and (step > 0) != (steps[i - 1] > 0):
                erratic_switches += 1

        if erratic_switches > self.max_switches_allowed and not st.already_flagged:
            st.already_flagged = True
            return {
                "type": "illegal_lane_change",
                "track_id": det.track_id,
                "vehicle_class": det.cls_name,
                "bbox": det.bbox,
                "switches": erratic_switches,
                "timestamp": now,
                "severity": "medium",
            }
        return None

    def forget(self, track_id: int):
        self._tracks.pop(track_id, None)


# --------------------------------------------------------------------------- #
# Combined manager
# --------------------------------------------------------------------------- #
class ViolationManager:
    def __init__(self, violations_cfg: dict, lanes, signal_state, sub_lanes: list | None = None):
        self.wrong_way = WrongWayDetector(violations_cfg.get("wrong_way", {}), lanes)
        self.red_light = RedLightViolationDetector(violations_cfg.get("red_light", {}), signal_state)
        self.lane_cutin = IllegalLaneCutInDetector(violations_cfg.get("illegal_lane_change", {}), sub_lanes or [])
        self.signal_state = signal_state
        self.total_by_type: Dict[str, int] = defaultdict(int)
        self.log: List[dict] = []  # capped rolling log for the dashboard/API

    def update(self, detections: List[Detection]) -> List[dict]:
        events = []
        for det in detections:
            for maybe_event in (
                self.wrong_way.update(det),
                self.red_light.update(det),
                self.lane_cutin.update(det),
            ):
                if maybe_event:
                    events.append(maybe_event)

        for ev in events:
            self.total_by_type[ev["type"]] += 1
            self.log.append(ev)
        if len(self.log) > 500:
            self.log = self.log[-500:]

        return events

    def forget_track(self, track_id: int):
        self.wrong_way.forget(track_id)
        self.red_light.forget(track_id)
        self.lane_cutin.forget(track_id)

    def snapshot(self) -> dict:
        return {
            "totals": dict(self.total_by_type),
            "signal_phase": self.signal_state.phase.value,
            "recent": self.log[-20:],
        }
