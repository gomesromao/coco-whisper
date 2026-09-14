"""Coconut Whisper: local push-to-talk dictation for the Coconut team."""
from __future__ import annotations

import faulthandler
import json
import logging
import os
import queue
import sys
import threading
import time
import tkinter as tk
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

from . import audio, hotkey, inject, postprocess
from .config import APP_NAME, Settings, data_dir, logs_dir, recordings_dir
from .overlay import Overlay
from .platform_support import (IS_MAC, claim_single_instance,
                               input_monitoring_ready, open_folder, play_tone,
                               show_message)
from .transcribe import Engine

log = logging.getLogger("cocowhisper")

VERSION = "0.1.7"

# Only the newest entries keep what was actually said. Older ones keep the
# timing and language, which is what support questions need, and the file is
# capped so it cannot grow forever.
HISTORY_TEXT_ENTRIES = 20
HISTORY_MAX_ENTRIES = 500

# How often the interface loop looks for work handed over by other threads.
# Short enough that the overlay still feels instant when the key goes down.
PUMP_MS = 40


def resource_path(*parts: str) -> Path:
    base = getattr(sys, "_MEIPASS", None)
    root = Path(base) if base else Path(__file__).resolve().parent.parent
    return root.joinpath(*parts)


NEWLINE = chr(10)

# Kept open for the life of the process: faulthandler writes straight to the
# file descriptor, so letting this be collected would silence it.
_crash_file = None


def setup_crash_log() -> None:
    """Catches the crashes Python never sees.

    A main thread rule broken in AppKit, or a fault inside PortAudio or Tk,
    kills the process without raising anything, which is why a Mac crash left
    us nothing to read. faulthandler writes the stack of every thread here
    before the process goes down.
    """
    global _crash_file
    try:
        _crash_file = open(logs_dir() / "crash.log", "a", encoding="utf-8")
        stamp = datetime.now().isoformat(timespec="seconds")
        _crash_file.write(
            NEWLINE + "=== " + stamp + " " + APP_NAME + " " + VERSION
            + " on " + sys.platform + " ===" + NEWLINE
        )
        _crash_file.flush()
        faulthandler.enable(file=_crash_file, all_threads=True)
    except OSError:
        log.debug("crash log unavailable", exc_info=True)


def setup_logging() -> None:
    handler = RotatingFileHandler(
        logs_dir() / "app.log", maxBytes=1_000_000, backupCount=2, encoding="utf-8"
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    if sys.stderr and sys.stderr.isatty():
        root.addHandler(logging.StreamHandler())
    for noisy in ("httpx", "httpcore", "huggingface_hub", "urllib3", "filelock"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def trim_history(path: Path) -> None:
    """Caps the file and drops the text from all but the newest entries."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return
    lines = [line for line in lines if line.strip()][-HISTORY_MAX_ENTRIES:]
    cutoff = len(lines) - HISTORY_TEXT_ENTRIES
    kept = []
    for index, line in enumerate(lines):
        if index < cutoff:
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            entry.pop("text", None)
            line = json.dumps(entry, ensure_ascii=False)
        kept.append(line)
    tmp = path.with_suffix(".jsonl.tmp")
    try:
        tmp.write_text("\n".join(kept) + "\n", encoding="utf-8")
        tmp.replace(path)
    except OSError:
        log.debug("history trim failed", exc_info=True)


def clear_history() -> int:
    """Removes every stored transcript. Returns how many entries went."""
    path = data_dir() / "history.jsonl"
    try:
        count = len([l for l in path.read_text(encoding="utf-8").splitlines() if l.strip()])
    except (OSError, UnicodeDecodeError):
        count = 0
    try:
        path.unlink(missing_ok=True)
    except OSError:
        log.debug("could not remove the history file", exc_info=True)
    return count


class App:
    def __init__(self) -> None:
        # Set before anything builds a window: every helper below decides what
        # is safe to touch by comparing against this thread.
        self._main_thread = threading.get_ident()
        self._pending: queue.Queue = queue.Queue()
        self.settings = Settings()
        self.engine = Engine()
        self.recorder = audio.Recorder()
        self.listener = hotkey.HotkeyListener(self.start_dictation, self.stop_dictation)
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title(APP_NAME)
        self.overlay = Overlay(self.root, self.later)
        self.tray = None
        self.state = "starting"
        self.last_text = ""
        self._busy = threading.Lock()
        self._auto_stop: threading.Timer | None = None
        self._icons: dict = {}

    # ---------- lifecycle ----------

    def on_main(self, fn) -> None:
        """Runs fn on the thread that owns the interface.

        The menu bar item is an AppKit object and AppKit refuses to be touched
        from anywhere but the main thread: it does not raise, it takes the
        process down with it, usually at the next click rather than at the
        offending call. Windows is more forgiving, but the transcription and
        preload threads have no business talking to the tray on either system.
        """
        if threading.get_ident() == self._main_thread:
            fn()
            return
        self.later(fn)

    def later(self, fn) -> None:
        """Hands fn to the interface loop, never running it inline.

        Nothing here touches Tk. root.after looks thread safe and is not: a
        call from another thread is marshalled across, and while it runs the
        thread state Tk hands back to Python is cleared. If the menu bar item
        reaches into AppKit during that window, AppKit turns the run loop over
        and a pending Tk timer fires with nothing to restore, which ends the
        process with a fatal error and no traceback. A plain queue drained by
        _pump keeps every Tk call on the thread that owns it.

        Windows are built through here on purpose too. A tray callback on
        macOS arrives while the menu is still open and still holding the run
        loop, which is the worst possible moment to put a window together.
        """
        self._pending.put(fn)

    def _pump(self) -> None:
        """Runs whatever other threads handed over. Interface thread only."""
        while True:
            try:
                fn = self._pending.get_nowait()
            except queue.Empty:
                break
            try:
                fn()
            except Exception:
                log.exception("queued interface work failed")
        try:
            self.root.after(PUMP_MS, self._pump)
        except (tk.TclError, RuntimeError):
            log.debug("interface gone, the queue stops here", exc_info=True)

    def run(self) -> None:
        self.listener.configure(
            self.settings.get("hotkey"), self.settings.get("hotkey_mode")
        )
        self.listener.start()
        threading.Thread(target=self._preload, daemon=True).start()
        self._start_tray()
        self._pump()
        self.root.after(400, self.check_permissions)
        self.root.mainloop()

    def _preload(self) -> None:
        try:
            self.set_state("loading")
            self.engine.load(self.settings.get("model"), self.settings.get("device"))
            self.set_state("idle")
            log.info("ready, hotkey=%s", self.settings.get("hotkey"))
        except Exception as exc:
            log.exception("model preload failed")
            self.set_state("error")
            self.notify("Model could not be loaded", str(exc)[:180])

    def quit(self) -> None:
        log.info("shutting down")
        self.listener.stop()
        if self.tray is not None:
            try:
                self.tray.visible = False
                self.tray.stop()
            except Exception:
                log.debug("tray did not stop cleanly", exc_info=True)
        self.later(self.root.destroy)

    def beep(self, kind: str) -> None:
        if self.settings.get("sounds"):
            play_tone(kind, self.settings.get("sound_volume"))

    # ---------- dictation ----------

    def start_dictation(self) -> None:
        if self.state in {"loading", "starting"}:
            self.notify(APP_NAME, "Still loading the model, one moment.")
            self.beep("error")
            return
        if self.state == "working" or self.recorder.is_recording:
            return
        try:
            self.recorder.start(self.settings.get("input_device"))
        except audio.RecordingError as exc:
            log.error("microphone unavailable: %s", exc)
            self.notify("Microphone unavailable", "Check your input device in Settings.")
            self.beep("error")
            return
        self.set_state("recording")
        self.beep("start")
        if self.settings.get("show_overlay"):
            self.overlay.show("listening")
        self._arm_auto_stop()

    def stop_dictation(self) -> None:
        self._disarm_auto_stop()
        if not self.recorder.is_recording:
            return
        buffer, peak = self.recorder.stop()
        self.beep("stop")
        seconds = buffer.size / audio.SAMPLE_RATE
        if seconds < audio.MIN_SECONDS:
            self.overlay.hide()
            self.set_state("idle")
            return
        if peak < 0.004:
            self.overlay.hide()
            self.set_state("idle")
            self.notify("Nothing was recorded", "The microphone picked up silence.")
            return
        threading.Thread(
            target=self._process, args=(buffer, seconds), daemon=True
        ).start()

    def _process(self, buffer, seconds: float) -> None:
        with self._busy:
            self.set_state("working")
            if self.settings.get("show_overlay"):
                self.overlay.show("working")
            started = time.time()
            try:
                result = self.engine.transcribe(
                    buffer,
                    self.settings.get("language"),
                    self.settings.get("model"),
                    self.settings.get("device"),
                )
            except Exception as exc:
                log.exception("transcription failed")
                self.overlay.hide()
                self.set_state("error")
                self.notify("Transcription failed", str(exc)[:180])
                self.beep("error")
                return

            text = postprocess.clean(
                result["text"],
                remove_fillers=self.settings.get("remove_fillers"),
                capitalize_first=self.settings.get("capitalize_first"),
                trailing_space=self.settings.get("trailing_space"),
                dictionary=self.settings.get("dictionary") or {},
            )
            elapsed = time.time() - started
            log.info(
                "audio %.1fs -> %d chars in %.1fs (lang=%s p=%.2f)",
                seconds,
                len(text),
                elapsed,
                result["language"],
                result["probability"],
            )

            if not text:
                self.overlay.hide()
                self.set_state("idle")
                self.notify("Nothing to insert", "No speech was recognised.")
                return

            self.last_text = text
            inject.deliver(text, self.settings.get("insert_mode"))
            self._record_history(text, result, seconds, elapsed, buffer)
            self.overlay.hide()
            self.set_state("idle")

    def _arm_auto_stop(self) -> None:
        limit = float(self.settings.get("max_seconds") or 180)
        self._disarm_auto_stop()
        timer = threading.Timer(limit, self._auto_stop_fired)
        timer.daemon = True
        timer.start()
        self._auto_stop = timer

    def _disarm_auto_stop(self) -> None:
        if self._auto_stop is not None:
            self._auto_stop.cancel()
            self._auto_stop = None

    def _auto_stop_fired(self) -> None:
        if self.recorder.is_recording:
            log.info("auto stop: recording hit the time limit")
            self.listener.reset()
            self.stop_dictation()

    def _record_history(self, text, result, seconds, elapsed, buffer) -> None:
        entry = {
            "at": datetime.now().isoformat(timespec="seconds"),
            "seconds": round(seconds, 2),
            "elapsed": round(elapsed, 2),
            "language": result.get("language"),
            "probability": round(float(result.get("probability") or 0), 3),
            "model": (self.engine.loaded_key or ("?",))[0],
            "chars": len(text),
        }
        if self.settings.get("keep_history_text"):
            entry["text"] = text
        try:
            path = data_dir() / "history.jsonl"
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
            trim_history(path)
        except OSError:
            log.debug("history write failed", exc_info=True)

        if self.settings.get("save_recordings"):
            try:
                stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                folder = recordings_dir()
                audio.save_wav(folder / (stamp + ".wav"), buffer)
                (folder / (stamp + ".txt")).write_text(text, encoding="utf-8")
            except Exception:
                log.debug("recording save failed", exc_info=True)

    # ---------- tray ----------

    def _icon_image(self, name: str):
        from PIL import Image

        if name not in self._icons:
            self._icons[name] = Image.open(resource_path("assets", "tray_" + name + ".png"))
        return self._icons[name]

    def status_text(self) -> str:
        key = hotkey.describe(self.settings.get("hotkey"))
        mode = self.settings.get("hotkey_mode")
        verb = "Hold" if mode == "hold" else "Press"
        labels = {
            "starting": "Starting...",
            "loading": "Loading model...",
            "idle": verb + " " + key + " to dictate",
            "recording": "Listening...",
            "working": "Transcribing...",
            "error": "Something went wrong, check the log",
        }
        return labels.get(self.state, self.state)

    def set_state(self, state: str) -> None:
        # The state itself is read by the dictation logic from whatever thread
        # it runs on, so it is set here. Only the drawing is handed over.
        self.state = state
        self.on_main(lambda: self._paint_tray(state))

    def _paint_tray(self, state: str) -> None:
        if self.tray is None:
            return
        icons = {
            "recording": "recording",
            "working": "busy",
            "loading": "busy",
            "starting": "busy",
        }
        try:
            self.tray.icon = self._icon_image(icons.get(state, "idle"))
            self.tray.title = APP_NAME + " - " + self.status_text()
            self.tray.update_menu()
        except Exception:
            log.debug("tray update failed", exc_info=True)

    def notify(self, title: str, message: str) -> None:
        self.on_main(lambda: self._show_notification(title, message))

    def _show_notification(self, title: str, message: str) -> None:
        if self.tray is None:
            return
        try:
            self.tray.notify(message, title)
        except Exception:
            log.debug("notification failed", exc_info=True)

    def _start_tray(self) -> None:
        import pystray
        from pystray import Menu, MenuItem

        from .transcribe import LANGUAGES

        def language_item(label: str, value: str):
            return MenuItem(
                label,
                lambda *_: self.set_language(value),
                checked=lambda item, v=value: self.settings.get("language") == v,
                radio=True,
            )

        menu = Menu(
            MenuItem(lambda item: self.status_text(), None, enabled=False),
            Menu.SEPARATOR,
            MenuItem("Language", Menu(*[language_item(l, v) for l, v in LANGUAGES])),
            MenuItem(
                "Copy last transcript",
                self._copy_last,
                enabled=lambda item: bool(self.last_text),
            ),
            Menu.SEPARATOR,
            MenuItem("Settings", self.open_settings, default=True),
            *([MenuItem("Permissions", self.open_permissions)] if IS_MAC else []),
            MenuItem("Open log folder", lambda *_: open_folder(logs_dir())),
            MenuItem("Version " + VERSION, None, enabled=False),
            Menu.SEPARATOR,
            MenuItem("Quit", lambda *_: self.quit()),
        )
        self.tray = pystray.Icon("coconut_whisper", self._icon_image("busy"), APP_NAME, menu)
        if IS_MAC:
            # macOS keeps its status bar item on the main run loop, which tkinter
            # also owns. run_detached is the supported way to share it.
            self.tray.run_detached()
        else:
            threading.Thread(target=self.tray.run, daemon=True).start()

    def _copy_last(self, *_args) -> None:
        if self.last_text:
            inject.deliver(self.last_text, "clipboard_only")

    def set_language(self, value: str) -> None:
        self.settings.set("language", value)
        log.info("language set to %s", value)

    def open_settings(self, *_args) -> None:
        from .ui import SettingsWindow

        log.info("opening settings")
        self.later(lambda: SettingsWindow(self.root, self))

    def open_permissions(self, *_args) -> None:
        from .ui import PermissionWindow

        self.later(lambda: PermissionWindow(self.root, self))

    def check_permissions(self) -> None:
        """On a Mac the hotkey is dead until the user allows it, and nothing
        on screen says so. Ask for it once, at the start."""
        if input_monitoring_ready():
            return
        log.info("accessibility permission is missing, asking for it")
        self.open_permissions()

    def apply_settings(self) -> None:
        """Called by the settings window after values change."""
        self.listener.configure(
            self.settings.get("hotkey"), self.settings.get("hotkey_mode")
        )
        current = self.engine.resolve(
            self.settings.get("model"), self.settings.get("device")
        )
        if self.engine.loaded_key != current:
            self.engine.unload()
            threading.Thread(target=self._preload, daemon=True).start()
        else:
            self.set_state(self.state)


def main() -> None:
    setup_logging()
    setup_crash_log()
    if not claim_single_instance():
        log.info("another instance is already running")
        show_message(
            APP_NAME,
            APP_NAME + " is already running. Look for the microphone icon in the "
            "menu bar or the system tray.",
        )
        return
    log.info("starting %s %s", APP_NAME, VERSION)
    App().run()


if __name__ == "__main__":
    main()
