"""Everything that differs between Windows and macOS lives here."""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
from pathlib import Path

log = logging.getLogger(__name__)

IS_WINDOWS = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"

APP_DIR_NAME = "CoconutWhisper"
LOCK_PORT = 49327  # a quiet high port, used only to detect a second instance


# ---------- folders ----------

def config_root() -> Path:
    if IS_WINDOWS:
        base = os.environ.get("APPDATA") or str(Path.home())
        return Path(base) / APP_DIR_NAME
    if IS_MAC:
        return Path.home() / "Library" / "Application Support" / APP_DIR_NAME
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / APP_DIR_NAME


def cache_root() -> Path:
    if IS_WINDOWS:
        base = os.environ.get("LOCALAPPDATA") or str(Path.home())
        return Path(base) / APP_DIR_NAME
    if IS_MAC:
        return Path.home() / "Library" / "Application Support" / APP_DIR_NAME
    return Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / APP_DIR_NAME


def open_folder(path) -> None:
    try:
        if IS_WINDOWS:
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif IS_MAC:
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except Exception:
        log.exception("could not open %s", path)


# ---------- sound ----------

# frequency, seconds, amplitude at full volume. Sine waves on purpose:
# winsound.Beep emits a square wave, which reads as something faulting rather
# than as a notification. The amplitudes were set by recording the tones back
# through the microphone and comparing them against that old beep.
TONES = {
    "start": (760, 0.07, 0.34),
    "stop": (520, 0.09, 0.26),
    "error": (330, 0.18, 0.40),
}
TONE_RATE = 44100
# The output device takes longer to open than a 90 ms tone lasts, so without a
# tail of silence the stream closes before a single sample is heard.
TONE_TAIL = 0.25


def play_tone(kind: str, volume: int = 20) -> None:
    """volume is a percentage, 0 silences the tone entirely."""
    volume = max(0, min(100, int(volume)))
    if volume == 0:
        return
    freq, seconds, full = TONES.get(kind, (700, 0.06, 0.25))
    amplitude = full * (volume / 100.0)

    def worker() -> None:
        try:
            import numpy as np
            import sounddevice as sd

            t = np.linspace(0, seconds, int(TONE_RATE * seconds), endpoint=False)
            wave = (amplitude * np.sin(2 * np.pi * freq * t)).astype("float32")
            # a fifth of the tone fades in and out, which removes the click at
            # both ends and is what makes it read as soft rather than harsh
            fade = max(1, int(len(wave) * 0.2))
            wave[:fade] *= np.linspace(0, 1, fade, dtype="float32")
            wave[-fade:] *= np.linspace(1, 0, fade, dtype="float32")
            tail = np.zeros(int(TONE_RATE * TONE_TAIL), dtype="float32")
            sd.play(np.concatenate([wave, tail]), TONE_RATE, blocking=True)
        except Exception:
            log.debug("tone failed", exc_info=True)

    threading.Thread(target=worker, daemon=True).start()


# ---------- single instance ----------

_lock_socket = None


def claim_single_instance() -> bool:
    """False when another copy is already running."""
    global _lock_socket
    import socket

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        # No SO_REUSEADDR on purpose: the bind must fail while a copy holds it.
        sock.bind(("127.0.0.1", LOCK_PORT))
        sock.listen(1)
        _lock_socket = sock
        return True
    except OSError:
        sock.close()
        return False


# ---------- keyboard ----------

def paste_modifier():
    """The modifier that means paste on this platform."""
    from pynput.keyboard import Key

    return Key.cmd if IS_MAC else Key.ctrl


def default_hotkey() -> str:
    return "right_cmd" if IS_MAC else "right_ctrl"


def hotkey_choices() -> list[tuple[str, str]]:
    if IS_MAC:
        return [
            ("Right Command (recommended)", "right_cmd"),
            ("Right Option", "right_alt"),
            ("Right Control", "right_ctrl"),
            ("Right Shift", "right_shift"),
            ("F9", "f9"),
            ("Control + Shift", "ctrl+shift"),
            ("Control + Space", "ctrl+space"),
            ("Option + Space", "alt+space"),
        ]
    return [
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


# ---------- start at login ----------

LAUNCH_AGENT = Path.home() / "Library" / "LaunchAgents" / "com.coconutva.whisper.plist"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = "CoconutWhisper"


def _launch_command() -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable]
    return [sys.executable, "-m", "app.main"]


def startup_enabled() -> bool:
    if IS_WINDOWS:
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
                winreg.QueryValueEx(key, RUN_VALUE)
                return True
        except OSError:
            return False
    return LAUNCH_AGENT.exists()


def set_startup(enabled: bool) -> bool:
    try:
        if IS_WINDOWS:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                                winreg.KEY_SET_VALUE) as key:
                if enabled:
                    command = " ".join('"' + part + '"' for part in _launch_command())
                    winreg.SetValueEx(key, RUN_VALUE, 0, winreg.REG_SZ, command)
                else:
                    try:
                        winreg.DeleteValue(key, RUN_VALUE)
                    except FileNotFoundError:
                        pass
            return True

        if not enabled:
            LAUNCH_AGENT.unlink(missing_ok=True)
            return True

        LAUNCH_AGENT.parent.mkdir(parents=True, exist_ok=True)
        args = "".join("    <string>" + part + "</string>\n"
                       for part in _launch_command())
        LAUNCH_AGENT.write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
            '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
            '<plist version="1.0">\n'
            "<dict>\n"
            "  <key>Label</key>\n"
            "  <string>com.coconutva.whisper</string>\n"
            "  <key>ProgramArguments</key>\n"
            "  <array>\n" + args + "  </array>\n"
            "  <key>RunAtLoad</key>\n"
            "  <true/>\n"
            "</dict>\n"
            "</plist>\n",
            encoding="utf-8",
        )
        return True
    except OSError:
        log.exception("could not change the start at login setting")
        return False


# ---------- dialogs ----------

def show_message(title: str, text: str) -> None:
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo(title, text)
        root.destroy()
    except Exception:
        log.info("%s: %s", title, text)
