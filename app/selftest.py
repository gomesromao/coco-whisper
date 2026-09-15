"""Runs the paths that have taken a Mac down, and reports whether we survived.

Every one of these has killed the process on a real machine at least once:
Carbon asked for the keyboard layout off the main thread, AppKit touched from
a worker, Tk driven from more than one thread. None of them raise anything.
The process simply stops, so the only honest check is to run them and see
whether we are still here afterwards.

The step name is printed before the step runs, and flushed. When a trap kills
us there is no traceback and no exit handler, so that line is the only thing
left saying where it happened.
"""
from __future__ import annotations

import os
import sys
import threading
import time
import traceback

# The whole point is to survive or not, so a hang has to count as a failure
# too. Nothing here should take anywhere near this long.
WATCHDOG_SECONDS = 150

_results: list[tuple[str, str]] = []


def _record(name: str, status: str, detail: str = "") -> None:
    _results.append((name, status))
    line = "[" + status + "] " + name
    if detail:
        line += ": " + detail
    print(line, flush=True)


def _step(name: str, fn, required: bool = True) -> bool:
    print("... " + name, flush=True)
    try:
        fn()
    except Exception as exc:
        _record(name, "FAIL" if required else "WARN", repr(exc))
        if required:
            traceback.print_exc()
        return False
    _record(name, "OK")
    return True


def _watchdog() -> None:
    def fire() -> None:
        print("[FAIL] the self test hung", flush=True)
        # _exit, not sys.exit: a stuck run loop would swallow the exception.
        os._exit(2)

    timer = threading.Timer(WATCHDOG_SECONDS, fire)
    timer.daemon = True
    timer.start()


def _on_worker(fn) -> None:
    """Runs fn on a thread and waits, the way the real app reaches the UI."""
    error: list[BaseException] = []

    def wrapped() -> None:
        try:
            fn()
        except BaseException as exc:  # noqa: BLE001 - reported below
            error.append(exc)

    thread = threading.Thread(target=wrapped, daemon=True)
    thread.start()
    thread.join(20)
    if thread.is_alive():
        raise TimeoutError("the worker thread never came back")
    if error:
        raise error[0]


def run() -> int:
    from .config import APP_NAME
    from .main import VERSION
    from .platform_support import (IS_MAC, focus_mechanism, frontmost_app,
                                   input_monitoring_ready, play_tone,
                                   prime_keyboard_layout, return_focus)

    _watchdog()
    print(APP_NAME + " " + VERSION + " runtime test on " + sys.platform, flush=True)
    print("accessibility: " + str(input_monitoring_ready()), flush=True)

    # ---------- the parts that need no window ----------

    # This is the call that traps on macOS 26 when it is not on the main
    # thread. Here it is on the main thread, which is the whole fix.
    def layout() -> None:
        ok = prime_keyboard_layout()
        if IS_MAC and not ok:
            raise RuntimeError("the keyboard layout could not be read")

    _step("read the keyboard layout on the main thread", layout)

    # The focus handback leans on an API Apple deprecated in macOS 14. Better
    # to learn here than from someone whose text went nowhere.
    def focus() -> None:
        how = focus_mechanism()
        print("focus API: " + how, flush=True)
        if IS_MAC and how in ("none", "unavailable"):
            raise RuntimeError("no way to hand the focus back: " + how)
        return_focus(frontmost_app())

    _step("find a way to hand the focus back", focus)

    from . import hotkey

    listener = hotkey.HotkeyListener(lambda: None, lambda: None)
    listener.configure("right_ctrl", "hold")

    # pynput reads the layout again from inside the thread it starts. Without
    # the priming above, this is where macOS 26 takes the process down.
    _step("start the hotkey listener", lambda: (listener.start(), time.sleep(2)))
    _step("restart the hotkey listener", lambda: (listener.restart(), time.sleep(2)))
    _step("stop the hotkey listener", listener.stop)

    # ---------- the parts that need the interface ----------

    import tkinter as tk

    from .main import App

    app = None
    try:
        app = App()
    except tk.TclError as exc:
        _record("build the interface", "FAIL", repr(exc))
        return _report()
    _record("build the interface", "OK")

    def settle(seconds: float = 1.5) -> None:
        end = time.time() + seconds
        while time.time() < end:
            try:
                app.root.update()
            except tk.TclError:
                return
            time.sleep(0.02)

    app._pump()
    settle(0.5)

    _step("start the menu bar item", lambda: (app._start_tray(), settle(2)))

    # set_state from a worker is what reaches the menu bar item through the
    # queue. Touching AppKit from that worker directly used to be fatal.
    def state_from_worker() -> None:
        _on_worker(lambda: app.set_state("idle"))
        settle()
        if not app._pending.empty():
            raise RuntimeError("the interface queue never drained")

    _step("repaint the menu bar from a worker thread", state_from_worker)

    def overlay_from_worker() -> None:
        _on_worker(lambda: app.overlay.show("listening"))
        settle()
        if not app.overlay._visible:
            raise RuntimeError("the overlay never appeared")
        _on_worker(app.overlay.hide)
        settle()
        if app.overlay._visible:
            raise RuntimeError("the overlay never went away")

    _step("show and hide the overlay from a worker thread", overlay_from_worker)

    _step("notify from a worker thread",
          lambda: (_on_worker(lambda: app.notify(APP_NAME, "self test")), settle()))

    # A build runner usually has no output device, so a silent failure here is
    # expected. What matters is that PortAudio does not take the process down.
    _step("play a tone", lambda: (play_tone("start", 20), time.sleep(2)), required=False)

    _step("open and close the settings window", lambda: _windows(app, settle))

    _step("shut down", lambda: _shutdown(app, settle))
    return _report()


def _windows(app, settle) -> None:
    from .ui import PermissionWindow, SettingsWindow

    window = SettingsWindow(app.root, app)
    window.withdraw()
    settle(0.5)
    window._close()
    settle(0.5)

    from .platform_support import IS_MAC

    if IS_MAC:
        # The window that polls for the permission and rebuilds the listener,
        # which is the sequence that crashed on a real Mac.
        permission = PermissionWindow(app.root, app)
        permission.withdraw()
        settle(2)
        permission._close()
        settle(0.5)


def _shutdown(app, settle) -> None:
    app.listener.stop()
    if app.tray is not None:
        try:
            app.tray.visible = False
            app.tray.stop()
        except Exception:
            pass
    settle(0.5)
    try:
        app.root.destroy()
    except Exception:
        pass


def _report() -> int:
    failed = [name for name, status in _results if status == "FAIL"]
    print("", flush=True)
    if failed:
        print("runtime test failed: " + ", ".join(failed), flush=True)
        return 1
    print("runtime test passed on " + sys.platform, flush=True)
    return 0
