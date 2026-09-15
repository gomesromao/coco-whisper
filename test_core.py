"""Quick checks for the pieces that do not need a GUI."""
import sys
import time

from app import hotkey, platform_support, postprocess

def check(name, got, want):
    status = "PASS" if got == want else "FAIL"
    print(f"[{status}] {name}")
    if got != want:
        print(f"       got:  {got!r}\n       want: {want!r}")
    return got == want

results = []
results.append(check("fillers + capital + space",
    postprocess.clean("um, please send the report uh before friday"),
    "Please send the report before friday "))
results.append(check("keeps text when all fillers",
    postprocess.clean("um", trailing_space=False),
    "Um"))
results.append(check("dictionary replace",
    postprocess.clean("send it to coconut v a team", dictionary={"coconut v a": "Coconut VA"}, trailing_space=False),
    "Send it to Coconut VA team"))
results.append(check("repeated words",
    postprocess.clean("the the client asked", trailing_space=False),
    "The client asked"))
results.append(check("space before punctuation",
    postprocess.clean("hello , world .", trailing_space=False),
    "Hello, world."))
results.append(check("portuguese untouched",
    postprocess.clean("preciso revisar a lista de leads", trailing_space=False),
    "Preciso revisar a lista de leads"))
results.append(check("hotkey parse combo",
    hotkey.parse("ctrl+shift+space"), {"ctrl", "shift", "space"}))
# F9 is the one key labelled the same on both systems. Right Ctrl is
# "Right Control" on a Mac, which used to fail here unnoticed.
results.append(check("hotkey describe", hotkey.describe("f9"), "F9"))
results.append(check("hotkey describe drops the recommendation",
    "(recommended)" in hotkey.describe(platform_support.default_hotkey()),
    False))


# ---------- the hotkey state machine ----------
# Tyler changed the hotkey with the old key still held, and the dictation it
# had started could never be ended: the tokens of the old key sat in _held
# where no release could clear them, and the app recorded for six minutes.
def held_is_cleared_on_change():
    listener = hotkey.HotkeyListener(lambda: None, lambda: None)
    listener.configure("right_ctrl", "hold")
    listener._held = {"right_ctrl": 0.0, "ctrl": 0.0}
    listener.configure("right_alt", "hold")
    return listener._held

results.append(check("changing the hotkey lets go of the old keys",
    held_is_cleared_on_change(), {}))


# A callback that raises used to go to stderr, which a packaged app does not
# have, and left _active stuck true so every later press was ignored.
def active_survives_a_failing_callback():
    def boom():
        raise RuntimeError("the stop path died")

    listener = hotkey.HotkeyListener(boom, boom)
    listener._fire(listener._on_start, True)
    for _ in range(200):
        if not listener._active:
            break
        time.sleep(0.01)
    return listener._active

results.append(check("a failing callback does not wedge the hotkey",
    active_survives_a_failing_callback(), False))

print("\n%d/%d passed" % (sum(results), len(results)))
# Without this the step is decorative: a failing check still printed and
# still let the build through.
sys.exit(0 if all(results) else 1)
