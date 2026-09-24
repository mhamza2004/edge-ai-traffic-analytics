#!/usr/bin/env python3
"""
Benchmark raw detection+tracking FPS on the current hardware, independent of
video I/O and overlay drawing. Use this on the Raspberry Pi itself (after
exporting to TFLite/NCNN with scripts/export_edge_model.py) to check whether
the >25 FPS target from the ticket is being met, and to compare model/imgsz
choices.

Usage:
    python -m scripts.benchmark_fps --weights yolov8n.pt --imgsz 640 --frames 100
    python -m scripts.benchmark_fps --weights yolov8n_ncnn_model --imgsz 320 --frames 200
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights", default="yolov8n.pt")
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--conf", type=float, default=0.35)
    ap.add_argument("--frames", type=int, default=100)
    ap.add_argument("--video", default=None, help="Optional: benchmark against a real video instead of synthetic noise")
    args = ap.parse_args()

    from app.detector import VehicleDetector

    class_map = {2: "Car", 3: "Motorbike", 5: "Bus", 7: "Truck"}
    detector = VehicleDetector(weights=args.weights, class_map=class_map, imgsz=args.imgsz, conf=args.conf)

    frames = []
    if args.video:
        import cv2
        cap = cv2.VideoCapture(args.video)
        while len(frames) < args.frames:
            ok, f = cap.read()
            if not ok:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                continue
            frames.append(f)
        cap.release()
    else:
        rng = np.random.default_rng(0)
        frames = [rng.integers(0, 255, (args.imgsz, args.imgsz, 3), dtype=np.uint8) for _ in range(args.frames)]

    print(f"Warming up ({args.weights}, imgsz={args.imgsz})...")
    detector.warmup(args.imgsz)

    print(f"Running {len(frames)} frames...")
    t0 = time.perf_counter()
    for f in frames:
        detector.infer(f)
    t1 = time.perf_counter()

    elapsed = t1 - t0
    fps = len(frames) / elapsed
    ms_per_frame = (elapsed / len(frames)) * 1000

    print("-" * 50)
    print(f"Weights      : {args.weights}")
    print(f"Image size   : {args.imgsz}")
    print(f"Frames       : {len(frames)}")
    print(f"Total time   : {elapsed:.2f}s")
    print(f"Avg latency  : {ms_per_frame:.1f} ms/frame")
    print(f"Throughput   : {fps:.1f} FPS  (this device)")
    print("-" * 50)
    print("Note: this measures raw detector+tracker throughput on THIS machine.")
    print("Run this same command on the target Raspberry Pi to get its real FPS number --")
    print("CPU/NPU throughput does not transfer between devices.")


if __name__ == "__main__":
    main()
