"""
MQTT telemetry publisher.

Publishes:
  {prefix}/metrics     - periodic aggregate counts / congestion snapshot (retained)
  {prefix}/violations  - one message per violation event, as it happens
  {prefix}/status      - simple online/offline LWT-style status

Connection failures never crash the pipeline -- if the broker is unreachable
the publisher logs once and silently no-ops, so the CV pipeline keeps running
even without MQTT available (useful when testing without a broker).
"""
from __future__ import annotations

import json
import logging
import threading
import time
from typing import Optional

import paho.mqtt.client as mqtt

logger = logging.getLogger("telemetry.mqtt")


class MQTTPublisher:
    def __init__(self, host: str, port: int, client_id: str, topic_prefix: str, enabled: bool = True):
        self.enabled = enabled
        self.host = host
        self.port = port
        self.topic_prefix = topic_prefix.rstrip("/")
        self._connected = False
        self._lock = threading.Lock()

        if not self.enabled:
            return

        self.client = mqtt.Client(client_id=client_id, protocol=mqtt.MQTTv311)
        self.client.will_set(f"{self.topic_prefix}/status", payload="offline", retain=True)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self._try_connect()

    def _try_connect(self):
        try:
            self.client.connect_async(self.host, self.port, keepalive=30)
            self.client.loop_start()
        except Exception as e:
            logger.warning("MQTT connect failed (%s) -- telemetry will be skipped until reconnected", e)

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self._connected = True
            client.publish(f"{self.topic_prefix}/status", "online", retain=True)
            logger.info("MQTT connected to %s:%s", self.host, self.port)
        else:
            logger.warning("MQTT connect returned rc=%s", rc)

    def _on_disconnect(self, client, userdata, rc):
        self._connected = False

    def publish_metrics(self, metrics: dict):
        if not self.enabled or not self._connected:
            return
        try:
            self.client.publish(f"{self.topic_prefix}/metrics", json.dumps(metrics), qos=0, retain=True)
        except Exception as e:
            logger.debug("MQTT publish_metrics failed: %s", e)

    def publish_violation(self, event: dict):
        if not self.enabled or not self._connected:
            return
        try:
            self.client.publish(f"{self.topic_prefix}/violations", json.dumps(event), qos=1)
        except Exception as e:
            logger.debug("MQTT publish_violation failed: %s", e)

    def close(self):
        if not self.enabled:
            return
        try:
            self.client.publish(f"{self.topic_prefix}/status", "offline", retain=True)
            self.client.loop_stop()
            self.client.disconnect()
        except Exception:
            pass
