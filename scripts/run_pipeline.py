#!/usr/bin/env python3
"""
Main entrypoint.

Two modes:

  1) Headless / batch mode -- just run the CV pipeline against a video file
     or camera, write the annotated output + CSV, and exit when the source
     ends. Good for quickly validating detection/counting/violation logic
     against a recorded clip.

        python -m scripts.run_pipeline --config config/config.yaml

  2) Serve mode -- run the pipeline in a background thread AND start the
     FastAPI dashboard/telemetry server, so you get the live web UI at
     http://<host>:8000/

        python -m scripts.run_pipeline --serve --config config/config.yaml

On a Raspberry Pi deployment you'd typically use --serve so the operator
dashboard stays reachable over the network the whole time the camera is live.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main():
    parser = argparse.ArgumentParser(description="Edge-AI Traffic Analytics Engine")
    parser.add_argument("--config", default=None, help="Path to config.yaml (default: config/config.yaml)")
    parser.add_argument("--serve", action="store_true", help="Also start the FastAPI dashboard/telemetry server")
    parser.add_argument("--max-frames", type=int, default=None, help="Stop after N processed frames (useful for quick tests)")
    args = parser.parse_args()

    if args.serve:
        import uvicorn
        if args.config:
            os.environ["TRAFFIC_CONFIG"] = args.config
        from app.config import load_config
        cfg = load_config(args.config)
        api_cfg = cfg.get("api", {})
        uvicorn.run("app.api.main:app", host=api_cfg.get("host", "0.0.0.0"), port=api_cfg.get("port", 8000))
    else:
        from app.pipeline import TrafficPipeline
        pipeline = TrafficPipeline(config_path=args.config)
        pipeline.run(max_frames=args.max_frames)


if __name__ == "__main__":
    main()
