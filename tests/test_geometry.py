"""
Quick sanity tests for the geometry helpers used by counting + violations.
Run with: python -m pytest tests/ -v   (or just: python -m tests.test_geometry)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.geometry import angle_between_deg, euclidean, point_in_polygon, segments_intersect


def test_point_in_polygon_inside():
    square = [(0, 0), (10, 0), (10, 10), (0, 10)]
    assert point_in_polygon((5, 5), square) is True


def test_point_in_polygon_outside():
    square = [(0, 0), (10, 0), (10, 10), (0, 10)]
    assert point_in_polygon((15, 5), square) is False


def test_segments_intersect_crossing():
    # a vertical line crossing a horizontal line through the middle
    assert segments_intersect((5, -5), (5, 5), (0, 0), (10, 0)) is True


def test_segments_intersect_parallel_no_cross():
    assert segments_intersect((0, 0), (10, 0), (0, 5), (10, 5)) is False


def test_angle_between_deg_opposite_vectors():
    angle = angle_between_deg((0, 1), (0, -1))
    assert abs(angle - 180) < 1e-6


def test_angle_between_deg_same_vector():
    angle = angle_between_deg((1, 0), (1, 0))
    assert abs(angle - 0) < 1e-6


def test_euclidean_distance():
    assert abs(euclidean((0, 0), (3, 4)) - 5.0) < 1e-6


def _run_all():
    tests = [v for k, v in globals().items() if k.startswith("test_")]
    passed = 0
    for t in tests:
        t()
        passed += 1
        print(f"PASS: {t.__name__}")
    print(f"\n{passed}/{len(tests)} tests passed.")


if __name__ == "__main__":
    _run_all()
