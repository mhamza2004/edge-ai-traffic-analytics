#!/usr/bin/env python3
"""
Red-light violation demonstration script.

The bundled demo_traffic.mp4 is real open-motorway footage with no actual
traffic signal controlling it -- traffic flows continuously. Running the
red-light detector there with the timer SIMULATOR produces a misleadingly
high "violation" rate (~35% of all vehicles), because the simulator's
GREEN/RED cycle has no real relationship to actual driver behavior on a road
that was never signal-controlled in the first place. That's a limitation of
using this specific clip for this specific violation type, not a detection
bug (the wrong-way and lane-cut-in logic were separately verified against
the full clip and are documented in the main README).

This script instead uses **manual** signal control (a supported signal_source
mode in the codebase) on the same real footage: the signal is held GREEN for
the whole clip except for one short, explicitly chosen window, during which
it's set RED -- so exactly the vehicle(s) genuinely crossing the stop-line in
that window get flagged, and everything else passes normally. This is a
controlled demonstration on real vehicle imagery, not a fabricated video,
and is clearly labeled as such everywhere it's referenced.

For a real signalized-intersection deployment, signal_source would instead
be "mqtt" or driven by an actual traffic-light-color classifier reading the
camera feed -- neither of which this open-motorway clip can honestly
demonstrate.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2
from app.config import load_config, resolve_path
from app.detector import VehicleDetector
from app.flow_counter import FlowCounter
from app.signal_state import SignalState, SignalPhase
from app.violations import ViolationManager
from app.speed_estimator import SpeedEstimator
from app.telemetry.events import EvidenceStore

RED_WINDOW_FRAMES = (40, 120)  # signal is RED only during this frame range; GREEN otherwise
                                 # (widened from the original 43-58: CPU inference isn't perfectly
                                 # deterministic run-to-run, so a narrow window could catch a
                                 # different subset of vehicles on a different machine/run. This
                                 # wider window reliably catches multiple vehicles -- Truck, Bus,
                                 # and several Cars -- regardless of minor tracking timing shifts.)
MAX_FRAMES = 1000

def main():
    cfg = load_config()
    class_map = {int(k): v for k, v in cfg["model"]["classes"].items()}
    detector = VehicleDetector(weights=cfg["model"]["weights"], class_map=class_map,
                                imgsz=cfg["video"]["imgsz"], conf=cfg["video"]["conf"], iou=cfg["video"]["iou"])
    flow = FlowCounter(cfg["lanes"], cfg["counting_lines"])
    signal = SignalState(mode="manual")
    signal.set_phase(SignalPhase.GREEN)
    # This demo script's whole purpose is to show red_light logic working, regardless of
    # whether it's left disabled by default in config.yaml for the main pipeline.
    violations_cfg = dict(cfg["violations"])
    violations_cfg["red_light"] = dict(violations_cfg["red_light"])
    violations_cfg["red_light"]["enabled"] = True
    violations = ViolationManager(violations_cfg, flow.lanes, signal)
    speed_est = SpeedEstimator(cfg.get("speed_estimation", {}))
    evidence = EvidenceStore(resolve_path("evidence"))

    src = resolve_path(cfg["video"]["source"])
    cap = cv2.VideoCapture(src)
    fps = cap.get(cv2.CAP_PROP_FPS) or 12
    w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    out_path = resolve_path("outputs/redlight_demo.mp4")
    writer = cv2.VideoWriter(out_path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))

    rl_cfg = cfg["violations"]["red_light"]
    stop_p1, stop_p2 = tuple(rl_cfg["stop_line"]["p1"]), tuple(rl_cfg["stop_line"]["p2"])

    frame_idx = 0
    detector.warmup()
    print(f"Signal held GREEN throughout, except RED during frames {RED_WINDOW_FRAMES[0]}-{RED_WINDOW_FRAMES[1]}")

    while frame_idx < MAX_FRAMES:
        ok, frame = cap.read()
        if not ok:
            break
        frame_idx += 1

        if RED_WINDOW_FRAMES[0] <= frame_idx <= RED_WINDOW_FRAMES[1]:
            signal.set_phase(SignalPhase.RED)
        else:
            signal.set_phase(SignalPhase.GREEN)

        dets = detector.infer(frame)
        flow.update(dets)
        speed_est.update(dets)
        events = violations.update(dets)
        for ev in events:
            if ev["type"] == "red_light":
                speed_kmh = speed_est.speed_for(ev["track_id"])
                if speed_kmh is not None:
                    ev["speed_kmh"] = round(speed_kmh, 1)
                evidence.save(frame, ev)
                speed_note = f" speed={ev['speed_kmh']}km/h" if "speed_kmh" in ev else " speed=n/a (didn't traverse the speed-check zone before violating)"
                print(f"  Frame {frame_idx}: RED LIGHT VIOLATION -- track={ev['track_id']} class={ev['vehicle_class']}{speed_note}")

        color = (0, 0, 255) if signal.is_red() else (0, 200, 0)
        cv2.line(frame, stop_p1, stop_p2, color, 3)
        cv2.putText(frame, f"SIGNAL: {signal.phase.value}", (stop_p1[0], stop_p1[1]-10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
        for det in dets:
            x1, y1, x2, y2 = map(int, det.bbox)
            cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 180, 0), 2)
            cv2.putText(frame, f"{det.cls_name} #{det.track_id}", (x1, max(0, y1-8)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 180, 0), 2)
        writer.write(frame)

    cap.release()
    writer.release()
    print(f"\nDone. {frame_idx} frames -> {out_path}")
    print(f"Total red_light violations: {violations.total_by_type.get('red_light', 0)}")

if __name__ == "__main__":
    main()
