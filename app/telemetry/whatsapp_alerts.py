"""
WhatsApp alerts via a self-hosted Evolution API instance.

Evolution API (https://github.com/EvolutionAPI/evolution-api) is an
open-source WhatsApp Business API gateway you run yourself. This client just
POSTs a text message (and optionally an evidence image) to your running
instance -- it does not include any credentials; you configure your own
`evolution_api_url`, `evolution_api_key` and `instance` in config.yaml or via
environment variables.

Disabled by default (telemetry.whatsapp.enabled: false in config.yaml).
Failures are logged and swallowed so a flaky network connection never takes
down the detection pipeline.
"""
from __future__ import annotations

import base64
import logging
import time
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger("telemetry.whatsapp")


class WhatsAppAlerter:
    def __init__(
        self,
        api_url: str,
        api_key: str,
        instance: str,
        to_number: str,
        alert_on: list[str],
        enabled: bool = False,
        min_seconds_between_alerts: float = 15.0,
        timeout: float = 5.0,
    ):
        self.enabled = enabled
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.instance = instance
        self.to_number = to_number
        self.alert_on = set(alert_on or [])
        self.min_seconds_between_alerts = min_seconds_between_alerts
        self.timeout = timeout
        self._last_sent_at = 0.0

    def _rate_limited(self) -> bool:
        return (time.time() - self._last_sent_at) < self.min_seconds_between_alerts

    def maybe_alert(self, event: dict, evidence_path: Optional[str] = None):
        if not self.enabled:
            return
        if event.get("type") not in self.alert_on:
            return
        if self._rate_limited():
            logger.debug("WhatsApp alert skipped (rate limited): %s", event.get("type"))
            return

        text = self._format_message(event)
        try:
            if evidence_path and Path(evidence_path).exists():
                self._send_image(evidence_path, caption=text)
            else:
                self._send_text(text)
            self._last_sent_at = time.time()
        except Exception as e:
            logger.warning("WhatsApp alert failed: %s", e)

    def _format_message(self, event: dict) -> str:
        ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(event.get("timestamp", time.time())))
        return (
            f"*Traffic Violation Alert*\n"
            f"Type: {event.get('type')}\n"
            f"Vehicle: {event.get('vehicle_class', 'unknown')}\n"
            f"Track ID: {event.get('track_id')}\n"
            f"Severity: {event.get('severity', 'n/a')}\n"
            f"Time: {ts}"
        )

    def _send_text(self, text: str):
        url = f"{self.api_url}/message/sendText/{self.instance}"
        headers = {"apikey": self.api_key, "Content-Type": "application/json"}
        payload = {"number": self.to_number, "text": text}
        resp = requests.post(url, json=payload, headers=headers, timeout=self.timeout)
        resp.raise_for_status()

    def _send_image(self, image_path: str, caption: str):
        url = f"{self.api_url}/message/sendMedia/{self.instance}"
        headers = {"apikey": self.api_key, "Content-Type": "application/json"}
        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
        payload = {
            "number": self.to_number,
            "mediatype": "image",
            "caption": caption,
            "media": b64,
            "fileName": Path(image_path).name,
        }
        resp = requests.post(url, json=payload, headers=headers, timeout=self.timeout)
        resp.raise_for_status()
