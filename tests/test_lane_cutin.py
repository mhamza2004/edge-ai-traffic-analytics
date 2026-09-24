"""
Validates IllegalLaneCutInDetector's core logic directly (bypassing video/YOLO) using
synthetic but clearly-labeled trajectories, since this violation type doesn't occur
naturally in the bundled real motorway clip (orderly flowing traffic rarely shows genuine
erratic lane-weaving within a few seconds -- see README). This proves the algorithm itself
is correct: it must ignore smooth same-direction drift (which is what a normal converging-
perspective camera produces for a vehicle staying in one real lane) and must catch a
genuine back-and-forth or multi-lane jump.
"""
import sys
import time
from pathlib import Path
from dataclasses import dataclass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.violations import IllegalLaneCutInDetector

SUB_LANES = [
    {"name": "Lane-1", "index": 1, "polygon": [(0, 480), (120, 480), (120, 0), (0, 0)]},
    {"name": "Lane-2", "index": 2, "polygon": [(120, 480), (240, 480), (240, 0), (120, 0)]},
    {"name": "Lane-3", "index": 3, "polygon": [(240, 480), (360, 480), (360, 0), (240, 0)]},
    {"name": "Lane-4", "index": 4, "polygon": [(360, 480), (480, 480), (480, 0), (360, 0)]},
]
ZONE = [(0, 480), (480, 480), (480, 0), (0, 0)]
CFG = {"enabled": True, "zone_polygon": ZONE, "max_switches_allowed": 1, "window_seconds": 4}


@dataclass
class FakeDetection:
    track_id: int
    cls_name: str
    x1: float; y1: float; x2: float; y2: float
    @property
    def center(self):
        return ((self.x1 + self.x2) / 2, (self.y1 + self.y2) / 2)
    @property
    def bbox(self):
        return (self.x1, self.y1, self.x2, self.y2)


def _det_at(track_id, x, y):
    return FakeDetection(track_id=track_id, cls_name="Car", x1=x - 10, y1=y - 10, x2=x + 10, y2=y + 10)


def test_smooth_same_direction_drift_is_not_flagged():
    """A vehicle whose x drifts steadily across Lane-1->2->3->4 in ONE direction only --
    exactly what a converging-perspective camera produces for a vehicle in a single real
    lane -- must NOT be flagged."""
    det = IllegalLaneCutInDetector(CFG, SUB_LANES)
    xs = [60, 90, 130, 170, 210, 250, 290, 330, 370, 410, 450]
    result = None
    for x in xs:
        result = det.update(_det_at(1, x, 300)) or result
        time.sleep(0.01)
    assert result is None


def test_erratic_back_and_forth_is_flagged():
    """A vehicle weaving Lane-1 -> Lane-2 -> Lane-1 -> Lane-2 (genuine direction reversals)
    within the time window must be flagged."""
    det = IllegalLaneCutInDetector(CFG, SUB_LANES)
    xs = [60, 60, 150, 150, 60, 60, 150, 150]  # lane 1,1,2,2,1,1,2,2 -> reversals
    result = None
    for x in xs:
        result = det.update(_det_at(2, x, 300)) or result
        time.sleep(0.01)
    assert result is not None
    assert result["type"] == "illegal_lane_change"


def test_multi_lane_jump_is_flagged():
    """A single-step jump spanning more than one lane (Lane-1 -> Lane-4 directly) is
    inherently erratic and must be flagged even without a direction reversal."""
    det = IllegalLaneCutInDetector(CFG, SUB_LANES)
    xs = [60, 60, 410, 410, 60, 60]
    result = None
    for x in xs:
        result = det.update(_det_at(3, x, 300)) or result
        time.sleep(0.01)
    assert result is not None


def _run_all():
    tests = [v for k, v in globals().items() if k.startswith("test_")]
    for t in tests:
        t()
        print(f"PASS: {t.__name__}")
    print(f"\n{len(tests)}/{len(tests)} tests passed.")


if __name__ == "__main__":
    _run_all()
