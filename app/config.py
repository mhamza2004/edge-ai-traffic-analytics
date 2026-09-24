"""
Config loading utilities.

Loads config/config.yaml and exposes it as a plain dict, with a couple of
small helpers for the values most modules need repeatedly.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_config(path: str | None = None) -> Dict[str, Any]:
    """Load the YAML config file into a plain dict.

    Environment variables can override secrets/endpoints without editing the
    YAML file, e.g. EVOLUTION_API_KEY, EVOLUTION_API_URL, MQTT_HOST.
    """
    cfg_path = Path(path) if path else PROJECT_ROOT / "config" / "config.yaml"
    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    # Allow environment variables to override sensitive / deployment-specific values
    env_overrides = {
        ("telemetry", "mqtt", "host"): "MQTT_HOST",
        ("telemetry", "mqtt", "port"): "MQTT_PORT",
        ("telemetry", "whatsapp", "evolution_api_url"): "EVOLUTION_API_URL",
        ("telemetry", "whatsapp", "evolution_api_key"): "EVOLUTION_API_KEY",
        ("telemetry", "whatsapp", "instance"): "EVOLUTION_INSTANCE",
        ("telemetry", "whatsapp", "to_number"): "EVOLUTION_TO_NUMBER",
        ("video", "source"): "VIDEO_SOURCE",
        ("model", "weights"): "MODEL_WEIGHTS",
        ("api", "host"): "API_HOST",
        ("api", "port"): "API_PORT",
    }
    for keys, env_name in env_overrides.items():
        val = os.environ.get(env_name)
        if val is None:
            continue
        node = cfg
        for k in keys[:-1]:
            node = node[k]
        # cast to int if the existing value is an int
        old = node.get(keys[-1])
        if isinstance(old, int) and not isinstance(old, bool):
            try:
                val = int(val)
            except ValueError:
                pass
        node[keys[-1]] = val

    return cfg


def resolve_path(relative: str) -> str:
    """Resolve a config-relative path against the project root."""
    p = Path(relative)
    if p.is_absolute():
        return str(p)
    return str(PROJECT_ROOT / p)
