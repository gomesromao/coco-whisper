"""Small always-on-top status pill shown while dictating."""
from __future__ import annotations

import logging
import tkinter as tk

log = logging.getLogger(__name__)

NAVY = "#0B1E3F"
GREEN = "#50B080"
AMBER = "#F4C430"
RED = "#E54B4B"
CREAM = "#FAF6EE"

STATES = {
    "listening": (GREEN, "Listening"),
    "working": (AMBER, "Transcribing"),
    "error": (RED, "Error"),
}


class Overlay:
    """Borderless pill near the bottom of the primary screen."""

    def __init__(self, root: tk.Tk) -> None:
        self._root = root
        self._win: tk.Toplevel | None = None
        self._dot: tk.Canvas | None = None
        self._label: tk.Label | None = None
        self._visible = False
        self._build()

    def _build(self) -> None:
        win = tk.Toplevel(self._root)
        win.withdraw()
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.attributes("-alpha", 0.96)
        win.configure(bg=NAVY)

        frame = tk.Frame(win, bg=NAVY, padx=16, pady=10)
        frame.pack()
        self._dot = tk.Canvas(frame, width=12, height=12, bg=NAVY,
                              highlightthickness=0)
        self._dot.create_oval(1, 1, 11, 11, fill=GREEN, outline="")
        self._dot.pack(side="left", padx=(0, 10))
        self._label = tk.Label(frame, text="Listening", bg=NAVY, fg=CREAM,
                               font=("Segoe UI", 11, "bold"))
        self._label.pack(side="left")
        self._win = win

    def _place(self) -> None:
        win = self._win
        if win is None:
            return
        win.update_idletasks()
        w = win.winfo_width() or 160
        h = win.winfo_height() or 40
        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        win.geometry(f"+{int(sw / 2 - w / 2)}+{int(sh - h - 90)}")

    def show(self, state: str, detail: str | None = None) -> None:
        color, text = STATES.get(state, STATES["listening"])
        self._root.after(0, lambda: self._apply(color, detail or text))

    def _apply(self, color: str, text: str) -> None:
        win, dot, label = self._win, self._dot, self._label
        if win is None or dot is None or label is None:
            return
        try:
            dot.delete("all")
            dot.create_oval(1, 1, 11, 11, fill=color, outline="")
            label.configure(text=text)
            if not self._visible:
                win.deiconify()
                win.attributes("-topmost", True)
                self._visible = True
            self._place()
        except tk.TclError:
            log.debug("overlay update failed", exc_info=True)

    def hide(self) -> None:
        self._root.after(0, self._do_hide)

    def _do_hide(self) -> None:
        if self._win is not None and self._visible:
            try:
                self._win.withdraw()
            except tk.TclError:
                pass
            self._visible = False
