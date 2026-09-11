"""Opens the settings window on its own so the layout can be inspected."""
import sys
import tkinter as tk

sys.path.insert(0, ".")
from app.config import Settings
from app.ui import SettingsWindow

class FakeApp:
    def __init__(self):
        self.settings = Settings()
    def apply_settings(self):
        print("apply_settings called")

root = tk.Tk()
root.withdraw()
win = SettingsWindow(root, FakeApp())
root.after(60000, root.destroy)
root.mainloop()
