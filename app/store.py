"""Persistence: config.json (user settings) and pickups.json (fetched dates).

Both live in DATA_DIR (default ./data, in Docker /data). Nothing address-
specific is ever part of the code; it is entered in the UI and stored here.
Secrets are NOT stored here — they come from environment variables.
"""

from __future__ import annotations

import json
import os
import threading
from copy import deepcopy
from pathlib import Path

from app.models import DEFAULT_CATEGORIES, Pickup

DEFAULT_CONFIG: dict = {
    "address": None,  # {"key": "<BSR AddrKey>", "label": "Musterstr. 1, 12345 Berlin (Bezirk)"}
    "categories": list(DEFAULT_CATEGORIES),
    "paper": {
        "mode": "off",  # "portal" | "manual" | "off"
        "first_date": None,  # ISO date, manual mode only
        "interval_weeks": 4,
    },
}

_lock = threading.Lock()


def data_dir() -> Path:
    p = Path(os.environ.get("DATA_DIR", "data"))
    p.mkdir(parents=True, exist_ok=True)
    return p


def _read(name: str, default):
    path = data_dir() / name
    if not path.exists():
        return deepcopy(default)
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _write(name: str, obj) -> None:
    path = data_dir() / name
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    tmp.replace(path)


def load_config() -> dict:
    with _lock:
        cfg = _read("config.json", DEFAULT_CONFIG)
    merged = deepcopy(DEFAULT_CONFIG)
    merged.update({k: v for k, v in cfg.items() if k in merged})
    merged["paper"] = {**DEFAULT_CONFIG["paper"], **(cfg.get("paper") or {})}
    return merged


def save_config(cfg: dict) -> None:
    with _lock:
        _write("config.json", cfg)


def load_data() -> dict:
    """Shape: {"updated_at": iso|None, "sources": {name: {...status, "pickups": [...]}}}"""
    with _lock:
        return _read("pickups.json", {"updated_at": None, "sources": {}})


def save_data(data: dict) -> None:
    with _lock:
        _write("pickups.json", data)


def all_pickups(data: dict) -> list[Pickup]:
    out: list[Pickup] = []
    for src in data.get("sources", {}).values():
        out.extend(Pickup.from_dict(p) for p in src.get("pickups", []))
    out.sort(key=lambda p: (p.date, p.category))
    return out
