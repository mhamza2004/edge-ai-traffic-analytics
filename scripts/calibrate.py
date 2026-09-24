#!/usr/bin/env python3
"""
Calibration helper.

Every site's camera angle is different, so the lane polygons / counting
lines / violation zones in config/config.yaml need to be re-drawn per
deployment. This script grabs one frame from your source, saves it as an
image with a pixel grid overlaid, so you can read off coordinates by eye
and paste them into config.yaml.

Usage:
    python -m scripts.calibrate --source data/sample_video/demo_traffic.mp4
    python -m scripts.calibrate --source 0        # USB webcam
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="data/sample_video/demo_traffic.mp4")
    ap.add_argument("--out", default="outputs/calibration_frame.jpg")
    ap.add_argument("--grid-step", type=int, default=100)
    args = ap.parse_args()

    src = int(args.source) if str(args.source).isdigit() else args.source
    cap = cv2.VideoCapture(src)
    ok, frame = cap.read()
    cap.release()
    if not ok:
        print(f"Could not read a frame from source: {args.source}")
        return

    h, w = frame.shape[:2]
    for x in range(0, w, args.grid_step):
        cv2.line(frame, (x, 0), (x, h), (60, 60, 60), 1)
        cv2.putText(frame, str(x), (x + 3, 15), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)
    for y in range(0, h, args.grid_step):
        cv2.line(frame, (0, y), (w, y), (60, 60, 60), 1)
        cv2.putText(frame, str(y), (3, y + 15), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(args.out, frame)
    print(f"Frame size: {w}x{h}")
    print(f"Saved calibration frame with a {args.grid_step}px grid to: {args.out}")
    print("Open it and read off pixel coordinates for your lanes / counting lines / violation zones,")
    print("then paste them into config/config.yaml.")


if __name__ == "__main__":
    main()
