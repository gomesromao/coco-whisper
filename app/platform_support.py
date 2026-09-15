"""Everything that differs between Windows and macOS lives here."""
from __future__ import annotations

import logging
import os
import shlex
import subprocess
import sys
import threading
import time
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


# ---------- who has the keyboard ----------

def frontmost_app():
    """The app holding the keyboard right now, or None where it does not apply.

    Only macOS needs this. On Windows a borderless window can come up without
    the caret moving; on macOS showing any window activates the whole app.
    """
    if not IS_MAC:
        return None
    try:
        from AppKit import NSWorkspace

        return NSWorkspace.sharedWorkspace().frontmostApplication()
    except Exception:
        log.debug("could not read the frontmost app", exc_info=True)
        return None


# activate() arrived in macOS 14 and is the one Apple wants used.
# activateWithOptions_ is what came before and is deprecated, so it is tried
# second and may well stop working on some future release.
_ACTIVATORS = ("activate", "activateWithOptions_")


def _activate(app) -> str:
    """Brings app forward. Returns the name of whatever actually worked."""
    for name in _ACTIVATORS:
        method = getattr(app, name, None)
        if method is None:
            continue
        try:
            method() if name == "activate" else method(0)
            return name
        except Exception:
            log.debug("%s was there but did not work", name, exc_info=True)
    return ""


def focus_mechanism() -> str:
    """Which activation API this machine offers, for the self test to report.

    One of the two is deprecated, so it is worth knowing which one a given
    macOS still answers to before finding out from a user.
    """
    if not IS_MAC:
        return "not needed"
    try:
        from AppKit import NSRunningApplication

        app = NSRunningApplication.currentApplication()
        for name in _ACTIVATORS:
            if getattr(app, name, None) is not None:
                return name
        return "none"
    except Exception:
        log.debug("could not read the activation API", exc_info=True)
        return "unavailable"


def return_focus(app) -> None:
    """Puts app back in front, but only when we are the ones in its way.

    Deliberately narrow. If the user has moved to something else since they
    started speaking, that is their business and pulling them back would be
    worse than pasting nowhere.
    """
    if not IS_MAC or app is None:
        return
    try:
        from AppKit import NSRunningApplication, NSWorkspace

        mine = NSRunningApplication.currentApplication()
        current = NSWorkspace.sharedWorkspace().frontmostApplication()
        if current is None or current.processIdentifier() != mine.processIdentifier():
            return
        if app.processIdentifier() == mine.processIdentifier():
            return
        used = _activate(app)
        if not used:
            log.warning("no way to hand the focus back to %s", app.localizedName())
            return
        log.info("handed the focus back to %s using %s", app.localizedName(), used)
        # Activation is asynchronous, and the paste needs the caret to be there.
        time.sleep(0.15)
    except Exception:
        log.debug("could not hand the focus back", exc_info=True)


# ---------- where we are installed ----------

APPLICATIONS = Path("/Applications")


def bundle_path():
    """The .app we are running from, or None outside a frozen Mac build."""
    if not IS_MAC or not getattr(sys, "frozen", False):
        return None
    for parent in Path(sys.executable).resolve().parents:
        if parent.suffix == ".app":
            return parent
    return None


def is_translocated() -> bool:
    """True when Gatekeeper mounted us on a throwaway read only copy.

    This is what happens when the app is opened straight from the folder it
    was unzipped into. The copy gets a fresh random path on every launch, and
    the accessibility permission is filed against a path, so nothing the user
    allows survives to the next launch.
    """
    path = bundle_path()
    return path is not None and "/AppTranslocation/" in str(path)


def installed_properly() -> bool:
    """True when we run from Applications, which is where the grant sticks.

    Running from source counts as fine: there is nothing to install and the
    permission belongs to the interpreter, not to us.
    """
    path = bundle_path()
    if path is None:
        return True
    return APPLICATIONS in path.parents


def open_applications_folder() -> None:
    open_folder(APPLICATIONS)


# ---------- coming back as a new process ----------

def can_relaunch() -> bool:
    """True when we know of an .app we could open again."""
    return bundle_path() is not None


def relaunch() -> bool:
    """Arranges for a fresh copy to open once this one has exited.

    macOS settles what a process is allowed to watch when the process starts.
    Granting the permission to a running app flips AXIsProcessTrusted to yes
    while the keyboard tap stays empty, so rebuilding the listener in place
    does nothing: only a new process gets the keys. That is why the app went
    silent right after saying the permission had gone through.

    The helper waits for this process to die before opening the new copy,
    because the single instance lock on LOCK_PORT is only released then.
    Returns True when the helper is on its way, and the caller still has to
    quit.
    """
    bundle = bundle_path()
    if bundle is None:
        return False
    script = (
        "while kill -0 " + str(os.getpid()) + " 2>/dev/null; do sleep 0.2; done; "
        "open -n " + shlex.quote(str(bundle))
    )
    try:
        subprocess.Popen(
            ["/bin/sh", "-c", script],
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        log.info("a fresh copy will open once this one exits")
        return True
    except Exception:
        log.exception("could not arrange the relaunch")
        return False


# ---------- permissions ----------

# The pane that lists the apps allowed to watch the keyboard. Opening it
# straight from the app saves the user from hunting through System Settings.
ACCESSIBILITY_PANE = (
    "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
)


def input_monitoring_ready() -> bool:
    """False on macOS while the app is not allowed to watch the keyboard.

    Without this permission pynput still starts and simply never reports a key,
    so the app looks alive and does nothing at all. Always true elsewhere.
    """
    if not IS_MAC:
        return True
    try:
        import HIServices

        return bool(HIServices.AXIsProcessTrusted())
    except Exception:
        # A missing check must never be the reason someone cannot dictate.
        log.debug("could not read the accessibility permission", exc_info=True)
        return True


_layout_context = None
_original_keycode_context = None


def prime_keyboard_layout() -> bool:
    """Reads the keyboard layout here, on the thread macOS insists on.

    pynput asks Carbon for the layout from inside its own listener thread.
    On macOS 26 that call runs dispatch_assert_queue against the main queue
    and traps, which takes the process down with no exception and nothing in
    the log. Reading it once up front and handing pynput the answer keeps the
    listener thread away from Carbon altogether. What pynput does with the
    value afterwards is UCKeyTranslate, which is pure and safe on any thread.

    The layout is a snapshot, so switching input source while the app runs
    leaves it stale until the next call. Worth it: the alternative is the app
    dying the moment the hotkey listener starts.
    """
    global _layout_context, _original_keycode_context
    if not IS_MAC:
        return True
    try:
        import contextlib

        from pynput.keyboard import _darwin

        if _original_keycode_context is None:
            _original_keycode_context = _darwin.keycode_context

        with _original_keycode_context() as context:
            keyboard_type, layout_data = context

        if layout_data is None:
            # Nothing useful to cache. Leaving pynput alone is no worse than
            # replacing it with a context that cannot translate anything.
            log.warning("no keyboard layout came back, leaving pynput alone")
            return False

        _layout_context = (keyboard_type, layout_data)

        @contextlib.contextmanager
        def cached_context():
            yield _layout_context

        _darwin.keycode_context = cached_context
        log.info("keyboard layout read on the main thread")
        return True
    except Exception:
        log.exception("could not read the keyboard layout up front")
        return False


def open_accessibility_settings() -> None:
    try:
        subprocess.Popen(["open", ACCESSIBILITY_PANE])
    except Exception:
        log.exception("could not open the accessibility settings")


def request_accessibility() -> bool:
    """The same check, but letting macOS show its own permission dialog.

    That dialog is what files the app under Accessibility with the hash of the
    build actually running, which saves the user from finding it in the list by
    hand. Returns the same answer as input_monitoring_ready.
    """
    if not IS_MAC:
        return True
    try:
        import HIServices

        options = {HIServices.kAXTrustedCheckOptionPrompt: True}
        return bool(HIServices.AXIsProcessTrustedWithOptions(options))
    except Exception:
        log.debug("could not ask for the accessibility permission", exc_info=True)
        return input_monitoring_ready()


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

DIALOG_TIMEOUT = 20.0


def show_message(title: str, text: str, timeout: float = DIALOG_TIMEOUT) -> None:
    """A plain dialog that closes itself when nobody comes to click it.

    The already running notice used to wait forever for an OK, so every extra
    double click left a process standing around holding an invisible box.
    """
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        if timeout > 0:
            root.after(int(timeout * 1000), root.destroy)
        messagebox.showinfo(title, text, parent=root)
        root.destroy()
    except Exception:
        log.info("%s: %s", title, text)
