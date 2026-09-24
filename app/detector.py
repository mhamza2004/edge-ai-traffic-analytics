"""
Neural inference + tracking wrapper.

Wraps Ultralytics YOLO so the rest of the pipeline never has to know whether
it's running a PyTorch .pt file on a dev laptop or an exported NCNN/TFLite
model on a Raspberry Pi -- same call signature either way.

Tracking uses Ultralytics' built-in ByteTrack (model.track(..., persist=True)),
which is the same tracker several of the reference repos (Smart Traffic
Management, Traffic Intelligence, etc.) use for stable per-vehicle IDs.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np
from ultralytics import YOLO


@dataclass
class Detection:
    track_id: int
    cls_id: int
    cls_name: str
    conf: float
    x1: float
    y1: float
    x2: float
    y2: float

    @property
    def center(self) -> tuple:
        return ((self.x1 + self.x2) / 2.0, (self.y1 + self.y2) / 2.0)

    @property
    def bbox(self) -> tuple:
        return (self.x1, self.y1, self.x2, self.y2)


class VehicleDetector:
    """Thin wrapper: frame in -> list[Detection] out, with stable track IDs."""

    def __init__(
        self,
        weights: str,
        class_map: Dict[int, str],
        imgsz: int = 640,
        conf: float = 0.35,
        iou: float = 0.5,
        tracker_cfg: str = "bytetrack.yaml",
    ):
        self.model = YOLO(weights)
        self.class_map = class_map
        self.imgsz = imgsz
        self.conf = conf
        self.iou = iou
        self.tracker_cfg = tracker_cfg
        self._class_ids = set(class_map.keys())

    def infer(self, frame: np.ndarray) -> List[Detection]:
        """Run detection + tracking on a single BGR frame."""
        results = self.model.track(
            source=frame,
            imgsz=self.imgsz,
            conf=self.conf,
            iou=self.iou,
            classes=list(self._class_ids) if self._class_ids else None,
            tracker=self.tracker_cfg,
            persist=True,
            verbose=False,
        )

        detections: List[Detection] = []
        r = results[0]
        if r.boxes is None or r.boxes.id is None:
            return detections

        boxes = r.boxes.xyxy.cpu().numpy()
        ids = r.boxes.id.cpu().numpy().astype(int)
        classes = r.boxes.cls.cpu().numpy().astype(int)
        confs = r.boxes.conf.cpu().numpy()

        for box, tid, cls_id, cf in zip(boxes, ids, classes, confs):
            cls_name = self.class_map.get(int(cls_id), str(cls_id))
            x1, y1, x2, y2 = box.tolist()
            detections.append(
                Detection(
                    track_id=int(tid),
                    cls_id=int(cls_id),
                    cls_name=cls_name,
                    conf=float(cf),
                    x1=x1, y1=y1, x2=x2, y2=y2,
                )
            )
        return detections

    def warmup(self, imgsz: Optional[int] = None):
        """Run one dummy inference so the first real frame isn't slow (helps
        real FPS measurements on Raspberry Pi where model init is costly)."""
        dummy = np.zeros((imgsz or self.imgsz, imgsz or self.imgsz, 3), dtype=np.uint8)
        self.model.predict(source=dummy, imgsz=self.imgsz, verbose=False)
