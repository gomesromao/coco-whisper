"""Global hotkey listener with hold-to-talk and toggle support."""
from __future__ import annotations

import logging
import threading

from pynput import keyboard

log = logging.getLogger(__name__)

HOTKEY_CHOICES = [
    ("Right Ctrl (recommended)", "right_ctrl"),
    ("Right Alt", "right_alt"),
    ("Right Shift", "right_shift"),
    ("F8", "f8"),
    ("F9", "f9"),
    ("Ctrl + Shift", "ctrl+shift"),
    ("Ctrl + Space", "ctrl+space"),
    ("Ctrl + Shift + Space", "ctrl+shift+space"),
    ("Alt + Space", "alt+space"),
]

_MODIFIER_TOKENS = {
    keyboard.Key.ctrl_l: {"ctrl", "left_ctrl"},
    keyboard.Key.ctrl_r: {"ctrl", "right_ctrl"},
    keyboard.Key.alt_l: {"alt", "left_alt"},
    keyboard.Key.alt_r: {"alt", "right_alt", "altgr"},
    keyboard.Key.alt_gr: {"alt", "right_alt", "altgr"},
    keyboard.Key.shift_l: {"shift", "left_shift"},
    keyboard.Key.shift_r: {"shift", "right_shift"},
    keyboard.Key.cmd_l: {"win", "left_win"},
    keyboard.Key.cmd_r: {"win", "right_win"},
}


def _tokens_for(key) -> set[str]:
    if key in _MODIFIER_TOKENS:
        return set(_MODIFIER_TOKENS[key])
    if isinstance(key, keyboard.Key):
        return {key.name}
    char = getattr(key, "char", None)
    if char:
        return {char.lower()}
    vk = getattr(key, "vk", None)
    return {f"vk{vk}"} if vk is not None else set()


def parse(spec: str) -> set[str]:
    return {part.strip().lower() for part in spec.split("+") if part.strip()}


def describe(spec: str) -> str:
    for label, value in HOTKEY_CHOICES:
        if value == spec:
            return label.replace(" (recommended)", "")
    return spec.replace("_", " ").title()


class HotkeyListener:
    """Calls on_start/on_stop as the configured hotkey is held or toggled."""

    def __init__(self, on_start, on_stop) -> None:
        self._on_start = on_start
        self._on_stop = on_stop
        self._required: set[str] = parse("right_ctrl")
        self._mode = "hold"
        self._pressed: set[str] = set()
        self._active = False
        self._lock = threading.Lock()
        self._listener: keyboard.Listener | None = None

    def configure(self, spec: str, mode: str) -> None:
        with self._lock:
            self._required = parse(spec)
            self._mode = mode
            if self._active and mode == "hold":
                self._active = False
                threading.Thread(target=self._on_stop, daemon=True).start()

    def start(self) -> None:
        if self._listener is not None:
            return
        self._listener = keyboard.Listener(
            on_press=self._handle_press, on_release=self._handle_release
        )
        self._listener.daemon = True
        self._listener.start()
        log.info("hotkey listener started")

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None

    def _satisfied(self) -> bool:
        return bool(self._required) and self._required.issubset(self._pressed)

    def _handle_press(self, key) -> None:
        tokens = _tokens_for(key)
        if not tokens:
            return
        with self._lock:
            was = self._satisfied()
            self._pressed |= tokens
            now = self._satisfied()
            mode, active = self._mode, self._active
        if was or not now:
            return
        if mode == "toggle":
            self._fire(self._on_stop if active else self._on_start, not active)
        else:
            self._fire(self._on_start, True)

    def _handle_release(self, key) -> None:
        tokens = _tokens_for(key)
        if not tokens:
            return
        with self._lock:
            was = self._satisfied()
            self._pressed -= tokens
            now = self._satisfied()
            mode, active = self._mode, self._active
        if mode == "hold" and was and not now and active:
            self._fire(self._on_stop, False)

    def _fire(self, callback, active: bool) -> None:
        with self._lock:
            self._active = active
        threading.Thread(target=callback, daemon=True).start()

    def reset(self) -> None:
        with self._lock:
            self._pressed.clear()
            self._active = False
