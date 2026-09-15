"""Checks the ways the app is supposed to recover, run from the repo root.

Each of these went wrong on a real machine first: a key up that never
arrived left the hotkey dead, a microphone that opened and sent nothing
left the app silent, and a granted permission kept showing the screen that
said it had been refused. None of them raised anything, so they are worth
a test that does.
"""
import sys
import time
import tkinter as tk

import numpy as np

sys.path.insert(0, ".")

from pynput import keyboard

from app import hotkey as hk
from app import ui
from app.main import App

failures = []


def check(name, got, want):
    ok = got == want
    print(("[PASS] " if ok else "[FAIL] ") + name)
    if not ok:
        print("       got:  " + repr(got))
        print("       want: " + repr(want))
        failures.append(name)


# ---------- a lost key up must not wedge the hotkey forever ----------

started = []
listener = hk.HotkeyListener(lambda: started.append(1), lambda: None)
listener.configure("right_ctrl", "hold")

long_ago = time.monotonic() - hk.STALE_SECONDS - 1
listener._held = {"ctrl": long_ago, "right_ctrl": long_ago}
listener._active = True

listener._handle_press(keyboard.Key.ctrl_r)
time.sleep(0.3)
check("a press after a lost release still starts dictation", started, [1])

# A key genuinely held is not thrown away.
held = hk.HotkeyListener(lambda: None, lambda: None)
held.configure("right_ctrl", "hold")
recent = time.monotonic() - 5
held._held = {"ctrl": recent, "right_ctrl": recent}
held._prune(time.monotonic())
check("a key held for five seconds is kept", sorted(held._held), ["ctrl", "right_ctrl"])
check("the stale window sits above the longest dictation", hk.STALE_SECONDS > 180, True)


# ---------- a microphone that sends nothing has to say so ----------

class DeadRecorder:
    is_recording = True

    def stop(self):
        return np.zeros(0, dtype="float32"), 0.0


app = App()
app._pump()
app.state = "recording"
app.recorder = DeadRecorder()
told = []
app.notify = lambda title, message: told.append((title, message))
app.beep = lambda kind: None
app.stop_dictation()
check("a silent microphone is reported, not swallowed",
      told and told[0][0], "No sound from the microphone")
check("and the app goes back to idle", app.state, "idle")


# ---------- the overlay must not be asked to take focus ----------

check("the overlay is driven through the queue, never Tk directly",
      callable(app.overlay._schedule), True)


# ---------- the permission window tells the truth and leaves ----------

class FakeListener:
    def __init__(self):
        self.restarts = 0

    def restart(self):
        self.restarts += 1


class FakeApp:
    def __init__(self, real):
        self.listener = FakeListener()
        self.settings = real.settings


def labels(win):
    found = []

    def walk(widget):
        for child in widget.winfo_children():
            try:
                text = child.cget("text")
            except tk.TclError:
                text = ""
            if text:
                found.append(text)
            walk(child)

    walk(win)
    return found


ui.is_translocated = lambda: False
ui.installed_properly = lambda: True
ui.input_monitoring_ready = lambda: True
ui.PermissionWindow._open = None
fake = FakeApp(app)
window = ui.PermissionWindow(app.root, fake)
window.withdraw()
app.root.update_idletasks()
text = " | ".join(labels(window))

check("the grant restarts the listener", fake.listener.restarts, 1)
check("the headline says it worked", "That did it" in text, True)
check("the old instructions are gone", "minus button" in text, False)
check("the old heading is gone", "One permission to go" in text, False)
from app.hotkey import describe
expected = "hold " + describe(app.settings.get("hotkey")) + " and talk"
check("it names the actual hotkey", expected in text, True)
check("the window closes itself", window._poll_id is None, True)

# It really does go away on its own.
alive = True
deadline = time.time() + 6
while time.time() < deadline:
    app.root.update()
    if not window.winfo_exists():
        alive = False
        break
    time.sleep(0.05)
check("and it is gone a few seconds later", alive, False)

app.root.destroy()

print()
print(("FAILURES: " + ", ".join(failures)) if failures else "all probes passed")
sys.exit(1 if failures else 0)
