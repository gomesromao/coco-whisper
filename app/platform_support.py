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

TONES = {"start": (760, 0.07), "stop": (560, 0.07), "error": (330, 0.18)}


def play_tone(kind: str) -> None:
    freq, seconds = TONES.get(kind, (700, 0.06))

    def worker() -> None:
        try:
            if IS_WINDOWS:
                import winsound

                winsound.Beep(int(freq), int(seconds * 1000))
                return
            import numpy as np
            import sounddevice as sd

            rate = 44100
            t = np.linspace(0, seconds, int(rate * seconds), endpoint=False)
            wave = (0.18 * np.sin(2 * np.pi * freq * t)).astype("float32")
            # short fade so the tone does not click
            fade = max(1, int(rate * 0.008))
            wave[:fade] *= np.linspace(0, 1, fade)
            wave[-fade:] *= np.linspace(1, 0, fade)
            sd.play(wave, rate, blocking=True)
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
