"""
TrafficPipeline: the thing that actually runs the camera/video loop.

Responsibilities per frame:
  1. Read a frame from the source (video file, USB cam, RTSP, or Pi camera)
  2. Run detection + tracking (app.detector.VehicleDetector)
  3. Feed detections into FlowCounter -> per-lane/direction/class counts
  4. Feed detections into ViolationManager -> wrong-way / red-light / cut-in
  5. Save evidence snapshots + fire MQTT / WhatsApp telemetry for violations
  6. Draw overlays and (optionally) write an annotated output video
  7. Publish periodic aggregate metrics over MQTT
  8. Update SharedState so the FastAPI layer can serve /metrics, /violations
     and an MJPEG preview without touching OpenCV itself

Can be run standalone (scripts/run_pipeline.py) or spun up as a background
thread from the FastAPI app (app/api/main.py) so one process serves both the
CV workload and the live dashboard.
"""
from __future__ import annotations

import csv
import logging
import os
import threading
import time
from pathlib import Path
from typing import Optional

import cv2

from .config import load_config, resolve_path
from .detector import VehicleDetector
from .flow_counter import FlowCounter
from .signal_state import SignalState
from .violations import ViolationManager
from .speed_estimator import SpeedEstimator
from .telemetry.events import EvidenceStore
from .telemetry.mqtt_publisher import MQTTPublisher
from .telemetry.whatsapp_alerts import WhatsAppAlerter
from .shared_state import shared_state

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("pipeline")


def _open_source(source):
    """Accepts an int (webcam index), 'picam', or a path/RTSP url string."""
    if source == "picam":
        from picamera2 import Picamera2  # only needed on a real Raspberry Pi
        picam = Picamera2()
        cfg = picam.create_video_configuration(main={"size": (1280, 720), "format": "RGB888"})
        picam.configure(cfg)
        picam.start()
        return "picam", picam, 30.0

    src = int(source) if str(source).isdigit() else source
    cap = cv2.VideoCapture(src)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    return "cv2", cap, fps


def _read_frame(kind, handle):
    if kind == "picam":
        frame = handle.capture_array()
        return True, cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
    return handle.read()


def _release_source(kind, handle):
    if kind == "cv2":
        handle.release()
    elif kind == "picam":
        handle.stop()


class TrafficPipeline:
    def __init__(self, config_path: Optional[str] = None):
        self.cfg = load_config(config_path)
        self.stop_event = threading.Event()

        vcfg = self.cfg["video"]
        mcfg = self.cfg["model"]
        tcfg = self.cfg.get("tracker", {})
        ocfg = self.cfg["output"]
        telcfg = self.cfg["telemetry"]

        class_map = {int(k): v for k, v in mcfg["classes"].items()}
        # Known model shorthands (e.g. "yolov8n.pt") are resolved/auto-downloaded by Ultralytics
        # itself; anything that looks like an actual path (has a separator) is resolved against
        # the project root so it works the same whether you run from traffic-engine/ or elsewhere.
        weights = mcfg["weights"]
        if os.sep in weights or "/" in weights:
            weights = resolve_path(weights)
        self.detector = VehicleDetector(
            weights=weights,
            class_map=class_map,
            imgsz=vcfg.get("imgsz", 640),
            conf=vcfg.get("conf", 0.35),
            iou=vcfg.get("iou", 0.5),
            tracker_cfg=tcfg.get("type", "bytetrack.yaml"),
        )

        self.flow_counter = FlowCounter(self.cfg["lanes"], self.cfg["counting_lines"])
        self.signal_state = SignalState(
            mode=self.cfg["violations"]["red_light"].get("signal_source", "simulator"),
            sim_cfg=self.cfg["violations"]["red_light"].get("simulator", {}),
        )
        self.violation_manager = ViolationManager(
            self.cfg["violations"], self.flow_counter.lanes, self.signal_state,
            sub_lanes=self.cfg.get("sub_lanes", []),
        )
        self.speed_estimator = SpeedEstimator(self.cfg.get("speed_estimation", {}))
        self.evidence_store = EvidenceStore(resolve_path(ocfg["evidence_dir"]))

        mqtt_cfg = telcfg["mqtt"]
        self.mqtt = MQTTPublisher(
            host=mqtt_cfg["host"], port=mqtt_cfg["port"], client_id=mqtt_cfg.get("client_id", "edge-traffic-engine"),
            topic_prefix=mqtt_cfg["topic_prefix"], enabled=mqtt_cfg.get("enabled", True),
        )
        self.mqtt_publish_interval = mqtt_cfg.get("publish_interval_seconds", 1.0)

        wa_cfg = telcfg["whatsapp"]
        self.whatsapp = WhatsAppAlerter(
            api_url=wa_cfg["evolution_api_url"], api_key=wa_cfg["evolution_api_key"],
            instance=wa_cfg["instance"], to_number=wa_cfg["to_number"], alert_on=wa_cfg.get("alert_on", []),
            enabled=wa_cfg.get("enabled", False), min_seconds_between_alerts=wa_cfg.get("min_seconds_between_alerts", 15),
        )

        self.save_video = ocfg.get("save_annotated_video", True)
        self.annotated_path = resolve_path(ocfg["annotated_path"])
        self.stats_csv_path = resolve_path(ocfg["stats_csv"])
        self.draw_overlays = ocfg.get("draw_overlays", True)
        self.frame_skip = max(1, vcfg.get("frame_skip", 1))
        self.loop_video_file = vcfg.get("loop_video_file", False)
        self.source = vcfg["source"]

        Path(self.annotated_path).parent.mkdir(parents=True, exist_ok=True)
        Path(self.stats_csv_path).parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    def _draw_overlays(self, frame, detections, fps: float):
        for lane in self.flow_counter.lanes:
            pts = [tuple(map(int, p)) for p in lane.polygon]
            cv2.polylines(frame, [cv2_np(pts)], True, (80, 200, 120), 2)
        for line in self.flow_counter.lines:
            cv2.line(frame, tuple(map(int, line.p1)), tuple(map(int, line.p2)), (0, 255, 255), 3)

        rl = self.cfg["violations"]["red_light"]
        if rl.get("enabled"):
            p1, p2 = tuple(map(int, rl["stop_line"]["p1"])), tuple(map(int, rl["stop_line"]["p2"]))
            color = (0, 0, 255) if self.signal_state.is_red() else (0, 200, 0)
            cv2.line(frame, p1, p2, color, 3)
            cv2.putText(frame, f"SIGNAL: {self.signal_state.phase.value}", (p1[0], p1[1] - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

        for det in detections:
            x1, y1, x2, y2 = map(int, det.bbox)
            cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 180, 0), 2)
            label = f"{det.cls_name} #{det.track_id}"
            speed = self.speed_estimator.speed_for(det.track_id)
            if speed is not None:
                label += f"  {speed:.0f} km/h"
            cv2.putText(frame, label, (x1, max(0, y1 - 8)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 180, 0), 2)

        snap = self.flow_counter.snapshot()
        y = 30
        cv2.rectangle(frame, (5, 5), (330, 95), (0, 0, 0), -1)
        cv2.putText(frame, f"Total: {snap['total_count']}  Present: {snap['currently_present']}", (15, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        y += 25
        cv2.putText(frame, f"In: {snap['by_direction'].get('inbound', 0)}  Out: {snap['by_direction'].get('outbound', 0)}", (15, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        y += 25
        cv2.putText(frame, f"FPS: {fps:.1f}", (15, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        return frame

    # ------------------------------------------------------------------ #
    def run(self, max_frames: Optional[int] = None):
        kind, handle, src_fps = _open_source(self.source)
        writer = None
        csv_file = open(self.stats_csv_path, "w", newline="")
        csv_writer = csv.writer(csv_file)
        csv_writer.writerow(["timestamp", "event_type", "track_id", "vehicle_class", "lane_or_line", "extra"])

        frame_idx = 0
        processed = 0
        t_last_mqtt = 0.0
        t_window_start = time.time()
        frames_in_window = 0
        fps = 0.0

        logger.info("Pipeline starting | source=%s | model=%s", self.source, self.cfg["model"]["weights"])
        self.detector.warmup()

        try:
            while not self.stop_event.is_set():
                ok, frame = _read_frame(kind, handle)
                if not ok:
                    if kind == "cv2" and self.loop_video_file:
                        handle.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        continue
                    logger.info("End of stream.")
                    break

                frame_idx += 1
                if frame_idx % self.frame_skip != 0:
                    continue
                processed += 1

                detections = self.detector.infer(frame)

                count_events = self.flow_counter.update(detections)
                for ev in count_events:
                    csv_writer.writerow([ev["timestamp"], "count", ev["track_id"], ev["vehicle_class"], ev["lane"], ev["direction"]])
                    self.mqtt.publish_metrics(self.flow_counter.snapshot())

                self.speed_estimator.update(detections)

                violation_events = self.violation_manager.update(detections)
                for ev in violation_events:
                    speed_kmh = self.speed_estimator.speed_for(ev["track_id"])
                    if speed_kmh is not None:
                        ev["speed_kmh"] = round(speed_kmh, 1)
                    evidence_path = self.evidence_store.save(frame, ev)
                    csv_writer.writerow([ev["timestamp"], ev["type"], ev["track_id"], ev.get("vehicle_class"), evidence_path or "", ev.get("severity", "")])
                    self.mqtt.publish_violation(ev)
                    self.whatsapp.maybe_alert(ev, evidence_path)
                    shared_state.add_violation({**ev, "evidence_path": evidence_path})
                    logger.warning("VIOLATION: %s | track=%s | class=%s", ev["type"], ev["track_id"], ev.get("vehicle_class"))

                frames_in_window += 1
                now = time.time()
                if now - t_window_start >= 1.0:
                    fps = frames_in_window / (now - t_window_start)
                    frames_in_window = 0
                    t_window_start = now
                    shared_state.set_fps(fps)

                if now - t_last_mqtt >= self.mqtt_publish_interval:
                    self.mqtt.publish_metrics(self.flow_counter.snapshot())
                    t_last_mqtt = now

                out_frame = frame
                if self.draw_overlays:
                    out_frame = self._draw_overlays(frame.copy(), detections, fps)

                if self.save_video:
                    if writer is None:
                        h, w = out_frame.shape[:2]
                        writer = cv2.VideoWriter(self.annotated_path, cv2.VideoWriter_fourcc(*"mp4v"), src_fps or 25, (w, h))
                    writer.write(out_frame)

                ok_jpeg, buf = cv2.imencode(".jpg", out_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
                if ok_jpeg:
                    shared_state.set_frame(buf.tobytes())

                metrics_snapshot = {
                    "flow": self.flow_counter.snapshot(),
                    "violations": self.violation_manager.snapshot(),
                    "fps": round(fps, 1),
                    "frames_processed": processed,
                }
                shared_state.set_metrics(metrics_snapshot)

                if max_frames is not None and processed >= max_frames:
                    logger.info("Reached max_frames=%s, stopping.", max_frames)
                    break
        finally:
            _release_source(kind, handle)
            if writer is not None:
                writer.release()
            csv_file.close()
            self.mqtt.close()
            logger.info("Pipeline stopped. Total counted=%s | Violations=%s",
                        self.flow_counter.total_count, dict(self.violation_manager.total_by_type))

    def run_in_thread(self) -> threading.Thread:
        t = threading.Thread(target=self.run, daemon=True)
        t.start()
        return t

    def stop(self):
        self.stop_event.set()


def cv2_np(pts):
    import numpy as np
    return np.array(pts, dtype=int)
