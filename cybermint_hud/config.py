from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

DEFAULT_CONFIG: dict[str, Any] = {
    "version": 1,
    "appearance": {
        "accent_primary": "#ff2a4b",    # Cyberpunk neon red
        "accent_secondary": "#00f0ff",  # Cyberpunk neon cyan
        "surface": "#0d0e15",           # Dark cyber obsidian surface
        "opacity": 0.92,
        "scale": 1.0,                   # UI scale multiplier (0.75 - 2.5)
    },
    "positions": {
        "clock": {"x": 32, "y": 32},
        "system": {"x": 32, "y": 180},
        "controls": {"x": 320, "y": 32},
    },
    "behavior": {
        "refresh_interval_seconds": 2,
        "always_on_top": True,
    },
}

COLOR_KEYS = {"accent_primary", "accent_secondary", "surface"}


def config_path(environ: dict[str, str] | None = None) -> Path:
    env = os.environ if environ is None else environ
    base = env.get("XDG_CONFIG_HOME") or str(Path(env.get("HOME", str(Path.home()))) / ".config")
    return Path(base) / "cybermint-hud" / "config.json"


def _is_valid_hex_color(val: Any) -> bool:
    if not isinstance(val, str) or len(val) != 7 or val[0] != "#":
        return False
    return all(c in "0123456789abcdefABCDEF" for c in val[1:])


def validate_config(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict) or raw.get("version") != 1:
        raise ValueError("Configuration must be a JSON object with version 1")

    appearance_raw = raw.get("appearance")
    positions_raw = raw.get("positions")
    if not isinstance(appearance_raw, dict) or not isinstance(positions_raw, dict):
        raise ValueError("Config fields 'appearance' and 'positions' must be JSON objects")

    result = json.loads(json.dumps(DEFAULT_CONFIG))

    # Backward compatibility mappings
    if "accent" in appearance_raw and "accent_primary" not in appearance_raw:
        appearance_raw["accent_primary"] = appearance_raw["accent"]
    if "cyan" in appearance_raw and "accent_secondary" not in appearance_raw:
        appearance_raw["accent_secondary"] = appearance_raw["cyan"]
    if "accent_cyan" in appearance_raw and "accent_secondary" not in appearance_raw:
        appearance_raw["accent_secondary"] = appearance_raw["accent_cyan"]

    # Validate hex colors
    for key in COLOR_KEYS:
        if key in appearance_raw:
            val = appearance_raw[key]
            if not _is_valid_hex_color(val):
                raise ValueError(f"appearance.{key} must be a 6-digit hex color formatted as #RRGGBB")
            result["appearance"][key] = val.lower()

    # Validate opacity
    if "opacity" in appearance_raw:
        opacity = appearance_raw["opacity"]
        if isinstance(opacity, bool) or not isinstance(opacity, (int, float)) or not 0.65 <= opacity <= 1.0:
            raise ValueError("appearance.opacity must be a numeric value between 0.65 and 1.0")
        result["appearance"]["opacity"] = float(opacity)

    # Validate scale
    if "scale" in appearance_raw:
        scale = appearance_raw["scale"]
        if isinstance(scale, bool) or not isinstance(scale, (int, float)) or not 0.75 <= scale <= 2.5:
            raise ValueError("appearance.scale must be a numeric value between 0.75 and 2.5")
        result["appearance"]["scale"] = float(scale)

    # Validate positions
    for name in ("clock", "system", "controls"):
        point = positions_raw.get(name, result["positions"][name])
        if not isinstance(point, dict):
            raise ValueError(f"positions.{name} must be a JSON object with x and y coordinates")
        normalized: dict[str, int] = {}
        for axis in ("x", "y"):
            val = point.get(axis, result["positions"][name][axis])
            if isinstance(val, bool) or not isinstance(val, int) or not 0 <= val <= 10000:
                raise ValueError(f"positions.{name}.{axis} must be an integer between 0 and 10000")
            normalized[axis] = val
        result["positions"][name] = normalized

    # Validate behavior (optional)
    behavior_raw = raw.get("behavior")
    if isinstance(behavior_raw, dict):
        if "refresh_interval_seconds" in behavior_raw:
            interval = behavior_raw["refresh_interval_seconds"]
            if isinstance(interval, bool) or not isinstance(interval, int) or not 1 <= interval <= 60:
                raise ValueError("behavior.refresh_interval_seconds must be an integer between 1 and 60")
            result["behavior"]["refresh_interval_seconds"] = interval
        if "always_on_top" in behavior_raw:
            aot = behavior_raw["always_on_top"]
            if not isinstance(aot, bool):
                raise ValueError("behavior.always_on_top must be a boolean")
            result["behavior"]["always_on_top"] = aot

    return result


def effective_position(config: dict[str, Any], name: str) -> dict[str, int]:
    """Window position to use. Untouched default positions grow with appearance.scale so the
    default layout does not overlap at larger UI scales; positions the user changed are
    used exactly as written."""
    position = config["positions"][name]
    if position != DEFAULT_CONFIG["positions"][name]:
        return dict(position)
    scale = float(config["appearance"].get("scale", 1.0))
    return {"x": int(round(position["x"] * scale)), "y": int(round(position["y"] * scale))}


def load_config(path: Path | None = None, logger: logging.Logger | None = None) -> dict[str, Any]:
    log = logger or logging.getLogger("cybermint_hud")
    target = path or config_path()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.write_text(json.dumps(DEFAULT_CONFIG, indent=2) + "\n", encoding="utf-8")
            return json.loads(json.dumps(DEFAULT_CONFIG))
        return validate_config(json.loads(target.read_text(encoding="utf-8")))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        log.error("Could not load configuration at %s: %s. Using safe defaults; file was preserved.", target, exc)
        return json.loads(json.dumps(DEFAULT_CONFIG))
