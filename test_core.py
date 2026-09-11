"""Quick checks for the pieces that do not need a GUI."""
from app import postprocess, hotkey

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
results.append(check("hotkey describe",
    hotkey.describe("right_ctrl"), "Right Ctrl"))

print("\n%d/%d passed" % (sum(results), len(results)))
