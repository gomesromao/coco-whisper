"""Lists the controls in the settings window without touching the screen."""
import sys, tkinter as tk
sys.path.insert(0, ".")
from app.config import Settings
from app.ui import SettingsWindow

class FakeApp:
    def __init__(self):
        self.settings = Settings()
        self.last_text = ""
    def apply_settings(self): pass

root = tk.Tk(); root.withdraw()
win = SettingsWindow(root, FakeApp())
win.withdraw()  # keep it off the user's screen
root.update_idletasks()

def walk(widget, depth=0):
    for child in widget.winfo_children():
        text = ""
        try:
            text = child.cget("text")
        except tk.TclError:
            pass
        kind = child.winfo_class()
        if text and kind in ("TButton", "TCheckbutton", "TLabel", "Label"):
            print(f"{kind:14s} {text}")
        walk(child, depth + 1)

walk(win)
root.destroy()
