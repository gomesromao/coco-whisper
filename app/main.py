"""Coconut Whisper: local push-to-talk dictation for the Coconut team."""
from __future__ import annotations

import json
import logging
import os
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
from .platform_support import (IS_MAC, claim_single_instance, open_folder,
                               play_tone, show_message)
from .transcribe import Engine

log = logging.getLogger("cocowhisper")

VERSION = "0.1.2"


def resource_path(*parts: str) -> Path:
    base = getattr(sys, "_MEIPASS", None)
    root = Path(base) if base else Path(__file__).resolve().parent.parent
    return root.joinpath(*parts)


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


class App:
    def __init__(self) -> None:
        self.settings = Settings()
        self.engine = Engine()
        self.recorder = audio.Recorder()
        self.listener = hotkey.HotkeyListener(self.start_dictation, self.stop_dictation)
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title(APP_NAME)
        self.overlay = Overlay(self.root)
        self.tray = None
        self.state = "starting"
        self.last_text = ""
        self._busy = threading.Lock()
        self._auto_stop: threading.Timer | None = None
        self._icons: dict = {}

    # ---------- lifecycle ----------

    def run(self) -> None:
        self.listener.configure(
            self.settings.get("hotkey"), self.settings.get("hotkey_mode")
        )
        self.listener.start()
        threading.Thread(target=self._preload, daemon=True).start()
        self._start_tray()
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
            self.tray.visible = False
            self.tray.stop()
        self.root.after(0, self.root.destroy)

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
        try:
            with (data_dir() / "history.jsonl").open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({**entry, "text": text}, ensure_ascii=False) + "\n")
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
        self.state = state
        icons = {
            "recording": "recording",
            "working": "busy",
            "loading": "busy",
            "starting": "busy",
        }
        if self.tray is not None:
            try:
                self.tray.icon = self._icon_image(icons.get(state, "idle"))
                self.tray.title = APP_NAME + " - " + self.status_text()
                self.tray.update_menu()
            except Exception:
                log.debug("tray update failed", exc_info=True)

    def notify(self, title: str, message: str) -> None:
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

        self.root.after(0, lambda: SettingsWindow(self.root, self))

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
