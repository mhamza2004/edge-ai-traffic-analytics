"""
Evidence snapshot handling for violation events.

Saves an annotated crop (plus a bit of padding) of the offending vehicle at
the moment a violation is confirmed: bounding box, class, speed estimate
(when available), and a timestamp burned into the image, alongside the full
frame for context.
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Optional

import cv2
import numpy as np


class EvidenceStore:
    def __init__(self, evidence_dir: str):
        self.evidence_dir = Path(evidence_dir)
        self.evidence_dir.mkdir(parents=True, exist_ok=True)

    def save(self, frame: np.ndarray, event: dict) -> Optional[str]:
        bbox = event.get("bbox")
        if bbox is None:
            return None
        x1, y1, x2, y2 = [int(v) for v in bbox]
        h, w = frame.shape[:2]
        pad = 25
        cx1, cy1 = max(0, x1 - pad), max(0, y1 - pad)
        cx2, cy2 = min(w, x2 + pad), min(h, y2 + pad)

        annotated = frame.copy()
        cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 0, 255), 3)
        label = f"{event['type'].upper()} | {event.get('vehicle_class', '')} | ID:{event.get('track_id')}"
        speed_kmh = event.get("speed_kmh")
        if speed_kmh is not None:
            label += f" | {speed_kmh:.0f} km/h (est.)"
        cv2.putText(annotated, label, (x1, max(0, y1 - 10)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
        ts_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(event.get("timestamp", time.time())))
        cv2.putText(annotated, ts_str, (10, h - 15),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

        crop = annotated[cy1:cy2, cx1:cx2]
        if crop.size == 0:
            crop = annotated

        fname = f"{event['type']}_{event.get('track_id')}_{int(event.get('timestamp', time.time()))}.jpg"
        fpath = self.evidence_dir / fname
        cv2.imwrite(str(fpath), crop)
        return str(fpath)

