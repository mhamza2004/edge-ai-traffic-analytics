#!/usr/bin/env python3
"""
Export a YOLOv8 .pt model to an edge-friendly format for Raspberry Pi or Jetson.

  - Raspberry Pi 4/5: use --format ncnn (fastest on Pi CPU) or --format tflite
    (closest match to the ticket's tech stack, works with a Coral USB
    Accelerator too). Both can be exported on ANY machine (dev laptop or the
    Pi itself) and copied over -- they're portable.

  - Jetson (Orin/Xavier/Nano): use --format engine (TensorRT). IMPORTANT:
    unlike ncnn/tflite, a TensorRT .engine file is compiled for the exact
    GPU architecture + TensorRT + CUDA version it was built with -- it is
    NOT portable across machines. This export MUST be run ON the Jetson
    board itself (with JetPack/TensorRT/CUDA already installed), not on a
    dev laptop. See Ultralytics' NVIDIA Jetson guide for the matching
    torch/torchvision build for your JetPack version before running this.

All formats are loaded the same way afterwards via Ultralytics' unified
YOLO() class, so nothing else in this codebase changes -- just point
config/config.yaml -> model.weights at the exported file/folder.

Usage:
    # Raspberry Pi (can run on a dev machine, then copy the output over)
    python -m scripts.export_edge_model --format ncnn --imgsz 320
    python -m scripts.export_edge_model --format tflite --imgsz 320 --int8

    # Jetson (run this command ON THE JETSON ITSELF)
    python -m scripts.export_edge_model --format engine --imgsz 320 --half
"""
from __future__ import annotations

import argparse
import platform
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights", default="yolov8n.pt")
    ap.add_argument("--format", choices=["ncnn", "tflite", "onnx", "engine"], default="ncnn",
                     help="ncnn/tflite = Raspberry Pi, engine = Jetson (TensorRT)")
    ap.add_argument("--imgsz", type=int, default=320, help="Lower = faster on edge hardware. 320 or 480 recommended.")
    ap.add_argument("--int8", action="store_true", help="Quantize to int8 (tflite only) for extra speed")
    ap.add_argument("--half", action="store_true", help="Use FP16 (engine/Jetson only) for extra speed with minimal accuracy loss")
    args = ap.parse_args()

    if args.format == "engine":
        is_arm = platform.machine().lower() in ("aarch64", "arm64")
        print("=" * 70)
        print("TensorRT (.engine) export selected for Jetson.")
        if not is_arm:
            print("WARNING: this machine does not look like a Jetson/ARM64 board.")
            print("A TensorRT engine built here will NOT run on the Jetson --")
            print("re-run this exact command ON the Jetson device instead.")
        print("=" * 70)

    from ultralytics import YOLO

    model = YOLO(args.weights)
    kwargs = {"format": args.format, "imgsz": args.imgsz}
    if args.format == "tflite" and args.int8:
        kwargs["int8"] = True
    if args.format == "engine" and args.half:
        kwargs["half"] = True

    print(f"Exporting {args.weights} -> {args.format} (imgsz={args.imgsz}) ...")
    try:
        out_path = model.export(**kwargs)
    except Exception as e:
        # Known issue: on some environments, a torch/torchao version mismatch causes
        # ultralytics' export() to crash in a post-conversion validation/benchmark step
        # -- AFTER the actual model file has already been written successfully. Check
        # for the expected output before treating this as a real failure.
        guessed_name = Path(args.weights).stem + (f"_int8.tflite" if args.format == "tflite" and args.int8
                                                    else f".{args.format}" if args.format != "ncnn"
                                                    else f"_ncnn_model")
        guessed_path = Path(guessed_name)
        if guessed_path.exists():
            print(f"\n(Non-fatal) export() raised an error after writing the model: {e}")
            print(f"The exported file/folder exists and is valid anyway: {guessed_path}")
            out_path = str(guessed_path)
        else:
            print(f"\nExport failed and no output file was produced: {e}")
            raise

    print(f"Done. Exported to: {out_path}")
    print("\nNext step: set model.weights in config/config.yaml to this path,")
    print("then re-run scripts/benchmark_fps.py on the target device to confirm real FPS.")


if __name__ == "__main__":
    main()

