"""Delivers transcribed text into whatever window has focus."""
from __future__ import annotations

import logging
import threading
import time

import pyperclip
from pynput.keyboard import Controller

from .platform_support import paste_modifier

log = logging.getLogger(__name__)
_keyboard = Controller()


def _restore_clipboard(previous: str, delay: float = 1.0) -> None:
    def worker() -> None:
        time.sleep(delay)
        try:
            pyperclip.copy(previous)
        except Exception:
            log.debug("could not restore clipboard", exc_info=True)

    threading.Thread(target=worker, daemon=True).start()


def deliver(text: str, mode: str = "paste") -> bool:
    """Insert text at the caret. Returns True when the text reached the app."""
    if not text:
        return False

    if mode == "type":
        try:
            _keyboard.type(text)
            return True
        except Exception:
            log.exception("typing failed, falling back to paste")
            mode = "paste"

    previous = ""
    try:
        previous = pyperclip.paste()
    except Exception:
        log.debug("clipboard read failed", exc_info=True)

    try:
        pyperclip.copy(text)
    except Exception:
        log.exception("clipboard write failed")
        return False

    if mode == "clipboard_only":
        return True

    time.sleep(0.05)
    try:
        with _keyboard.pressed(paste_modifier()):
            _keyboard.press("v")
            _keyboard.release("v")
    except Exception:
        log.exception("paste keystroke failed")
        return False

    if previous:
        _restore_clipboard(previous)
    return True
