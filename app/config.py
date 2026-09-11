"""Settings storage for Coconut Whisper."""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path

from .platform_support import cache_root, config_root, default_hotkey

APP_NAME = "Coconut Whisper"

DEFAULTS: dict = {
    "hotkey": default_hotkey(),
    "hotkey_mode": "hold",          # hold | toggle
    "language": "auto",             # auto | en | pt | tl | taglish
    "model": "auto",                # auto | tiny | base | small | medium | large-v3-turbo
    "device": "auto",               # auto | cpu | cuda
    "input_device": None,           # None = system default microphone
    "insert_mode": "paste",         # paste | type | clipboard_only
    "trailing_space": True,
    "capitalize_first": True,
    "remove_fillers": True,
    "sounds": True,
    "sound_volume": 20,       # percent of the loudest the tone can be
    "show_overlay": True,
    "launch_at_startup": False,
    "max_seconds": 180,
    "dictionary": {},               # spoken form -> written form
    "save_recordings": False,       # pilot mode: keep audio + text for accuracy testing
}


def data_dir() -> Path:
    path = config_root()
    path.mkdir(parents=True, exist_ok=True)
    return path


def models_dir() -> Path:
    path = cache_root() / "models"
    path.mkdir(parents=True, exist_ok=True)
    return path


def logs_dir() -> Path:
    path = data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def recordings_dir() -> Path:
    path = data_dir() / "recordings"
    path.mkdir(parents=True, exist_ok=True)
    return path


class Settings:
    """Thread-safe JSON-backed settings."""

    def __init__(self) -> None:
        self._path = data_dir() / "settings.json"
        self._lock = threading.Lock()
        self._data = dict(DEFAULTS)
        self.load()

    def load(self) -> None:
        if not self._path.exists():
            self.save()
            return
        try:
            # utf-8-sig so a file saved by a Windows editor, byte order mark and
            # all, does not silently fall back to the defaults.
            raw = json.loads(self._path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            logging.getLogger(__name__).warning(
                "settings file could not be read, using defaults: %s", self._path
            )
            return
        merged = dict(DEFAULTS)
        merged.update({k: v for k, v in raw.items() if k in DEFAULTS})
        with self._lock:
            self._data = merged

    def save(self) -> None:
        with self._lock:
            payload = json.dumps(self._data, indent=2, ensure_ascii=False)
        tmp = self._path.with_suffix(".json.tmp")
        tmp.write_text(payload, encoding="utf-8")
        tmp.replace(self._path)

    def get(self, key: str, default=None):
        with self._lock:
            return self._data.get(key, DEFAULTS.get(key, default))

    def set(self, key: str, value) -> None:
        with self._lock:
            self._data[key] = value
        self.save()

    def update(self, values: dict) -> None:
        with self._lock:
            self._data.update(values)
        self.save()

    def as_dict(self) -> dict:
        with self._lock:
            return dict(self._data)

    @property
    def path(self) -> Path:
        return self._path
