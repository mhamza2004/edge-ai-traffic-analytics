"""
Validates SpeedEstimator's core distance/time logic directly (bypassing video/YOLO)
using synthetic trajectories with a known, controlled speed -- lets us verify the
math is correct independent of any real camera's calibration accuracy.
"""
import sys
import time
from pathlib import Path
from dataclasses import dataclass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.speed_estimator import SpeedEstimator

CFG = {
    "enabled": True,
    "max_reasonable_kmh": 180,
    "zones": [
        {
            "name": "test-zone",
            "line_a": {"p1": [0, 400], "p2": [480, 400]},
            "line_b": {"p1": [0, 250], "p2": [480, 250]},
            "distance_m": 20.0,
        }
    ],
}


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


def _det_at(track_id, y):
    return FakeDetection(track_id=track_id, cls_name="Car", x1=190, y1=y - 10, x2=210, y2=y + 10)


def test_known_speed_computes_correctly():
    """20m in exactly 1 real second (via sleep) should compute to ~72 km/h (20m/s * 3.6)."""
    est = SpeedEstimator(CFG)
    est.update([_det_at(1, 450)])   # well below line_a, establishes last_center
    est.update([_det_at(1, 390)])   # step crosses through line_a (y=400)
    time.sleep(1.0)
    est.update([_det_at(1, 240)])   # step crosses through line_b (y=250) ~1 second later
    speed = est.speed_for(1)
    assert speed is not None
    # allow generous tolerance for real sleep() timing jitter in a test environment
    assert 55 <= speed <= 90, f"expected ~72 km/h, got {speed}"


def test_no_speed_without_completing_both_lines():
    """A vehicle that only crosses line_a (never reaches line_b) must not get a speed."""
    est = SpeedEstimator(CFG)
    est.update([_det_at(2, 450)])
    est.update([_det_at(2, 390)])   # crosses line_a only
    est.update([_det_at(2, 380)])   # still hasn't reached line_b
    assert est.speed_for(2) is None


def test_unreasonable_speed_is_discarded():
    """An implausibly high computed speed (e.g. from a tracker glitch with near-zero
    elapsed time) must be discarded, not reported as a real reading."""
    est = SpeedEstimator(CFG)
    est.update([_det_at(3, 450)])
    est.update([_det_at(3, 390)])   # crosses line_a
    est.update([_det_at(3, 240)])   # crosses line_b in the same/next call, ~0 elapsed time
    # either None (elapsed too small to count) or, if it did compute, must respect the cap
    speed = est.speed_for(3)
    if speed is not None:
        assert speed <= CFG["max_reasonable_kmh"]


def test_forget_clears_track():
    est = SpeedEstimator(CFG)
    est.update([_det_at(4, 450)])
    est.update([_det_at(4, 390)])
    time.sleep(1.0)
    est.update([_det_at(4, 240)])
    assert est.speed_for(4) is not None
    est.forget(4)
    assert est.speed_for(4) is None


def _run_all():
    tests = [v for k, v in globals().items() if k.startswith("test_")]
    for t in tests:
        t()
        print(f"PASS: {t.__name__}")
    print(f"\n{len(tests)}/{len(tests)} tests passed.")


if __name__ == "__main__":
    _run_all()
