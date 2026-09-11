"""Settings window."""
from __future__ import annotations

import logging
import os
import tkinter as tk
from tkinter import ttk

from . import audio, startup
from .config import APP_NAME, data_dir
from .hotkey import HOTKEY_CHOICES
from .transcribe import LANGUAGES, MODEL_CATALOG, cuda_available

log = logging.getLogger(__name__)

NAVY = "#0B1E3F"
NAVY_SOFT = "#122A52"
GREEN = "#50B080"
CREAM = "#FAF6EE"
BG = "#F7F7F4"
FG = "#07152B"
FG_MUTED = "#5C6B85"
BORDER = "#E6E8EE"
CONTENT_WIDTH = 520


class SettingsWindow(tk.Toplevel):
    _open: "SettingsWindow | None" = None

    def __init__(self, root: tk.Tk, app) -> None:
        if SettingsWindow._open is not None:
            try:
                SettingsWindow._open.lift()
                SettingsWindow._open.focus_force()
                return
            except tk.TclError:
                SettingsWindow._open = None
        super().__init__(root)
        SettingsWindow._open = self
        self.app = app
        self.settings = app.settings

        self.title(APP_NAME + " Settings")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self._close)
        try:
            self.iconbitmap(str(_icon_path()))
        except Exception:
            log.debug("window icon unavailable", exc_info=True)

        self._devices = audio.list_input_devices()
        self._build()
        self._center(root)
        self.lift()
        self.focus_force()

    # ---------- layout ----------

    def _build(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TFrame", background=BG)
        style.configure("Card.TFrame", background="#FFFFFF")
        style.configure("TLabel", background=BG, foreground=FG, font=("Segoe UI", 10))
        style.configure("Card.TLabel", background="#FFFFFF", foreground=FG,
                        font=("Segoe UI", 10))
        style.configure("Muted.TLabel", background="#FFFFFF", foreground=FG_MUTED,
                        font=("Segoe UI", 9))
        style.configure("Section.TLabel", background=BG, foreground=FG,
                        font=("Segoe UI", 11, "bold"))
        style.configure("TCheckbutton", background="#FFFFFF", foreground=FG,
                        font=("Segoe UI", 10))
        style.configure("TCombobox", fieldbackground="#FFFFFF")
        style.configure("Accent.TButton", background=GREEN, foreground="#FFFFFF",
                        font=("Segoe UI", 10, "bold"), borderwidth=0, padding=(18, 8))
        style.map("Accent.TButton", background=[("active", "#3F9A6E")])
        style.configure("Ghost.TButton", background=BG, foreground=FG,
                        font=("Segoe UI", 10), borderwidth=1, padding=(14, 8))

        header = tk.Frame(self, bg=NAVY, padx=20, pady=12)
        header.pack(fill="x")
        tk.Label(header, text=APP_NAME, bg=NAVY, fg="#FFFFFF",
                 font=("Segoe UI", 15, "bold")).pack(anchor="w")
        tk.Label(header, text="Local dictation. Nothing leaves this computer.",
                 bg=NAVY, fg="#C8D2E2", font=("Segoe UI", 9)).pack(anchor="w")

        body = ttk.Frame(self, padding=(16, 10, 16, 10))
        body.pack(fill="both", expand=True)

        self._vars: dict = {}
        self._build_dictation(body)
        self._build_output(body)
        self._build_advanced(body)

        footer = ttk.Frame(self, padding=(16, 0, 16, 14))
        footer.pack(fill="x")
        ttk.Button(footer, text="Save", style="Accent.TButton",
                   command=self._save).pack(side="right")
        ttk.Button(footer, text="Cancel", style="Ghost.TButton",
                   command=self._close).pack(side="right", padx=(0, 8))
        ttk.Button(footer, text="Open data folder", style="Ghost.TButton",
                   command=lambda: os.startfile(data_dir())).pack(side="left")

    def _card(self, parent, title: str) -> ttk.Frame:
        ttk.Label(parent, text=title, style="Section.TLabel").pack(
            anchor="w", pady=(8, 4))
        outer = tk.Frame(parent, bg=BORDER)
        outer.pack(fill="x")
        card = ttk.Frame(outer, style="Card.TFrame", padding=(12, 8), width=CONTENT_WIDTH)
        card.pack(fill="x", padx=1, pady=1)
        card.columnconfigure(1, weight=1)
        card._next_row = 0  # type: ignore[attr-defined]
        return card

    def _row(self, card, label: str, widget, hint: str | None = None) -> None:
        row = card._next_row  # type: ignore[attr-defined]
        ttk.Label(card, text=label, style="Card.TLabel").grid(
            row=row, column=0, sticky="w", padx=(0, 12), pady=3)
        widget.grid(row=row, column=1, sticky="ew", pady=3)
        row += 1
        if hint:
            ttk.Label(card, text=hint, style="Muted.TLabel",
                      wraplength=CONTENT_WIDTH - 40, justify="left").grid(
                row=row, column=0, columnspan=2, sticky="w", pady=(0, 4))
            row += 1
        card._next_row = row  # type: ignore[attr-defined]

    def _full(self, card, widget, pady=(0, 0)) -> None:
        row = card._next_row  # type: ignore[attr-defined]
        widget.grid(row=row, column=0, columnspan=2, sticky="ew", pady=pady)
        card._next_row = row + 1  # type: ignore[attr-defined]

    def _check(self, card, key: str, text: str) -> None:
        var = tk.BooleanVar(value=bool(self.settings.get(key)))
        self._vars[key] = var
        box = ttk.Checkbutton(card, text=text, variable=var)
        self._full(card, box, pady=1)

    def _build_dictation(self, parent) -> None:
        card = self._card(parent, "Dictation")

        self._hotkey_var = tk.StringVar(value=_label_for(HOTKEY_CHOICES, self.settings.get("hotkey")))
        combo = ttk.Combobox(card, textvariable=self._hotkey_var, state="readonly",
                             values=[l for l, _ in HOTKEY_CHOICES], width=30)
        self._row(card, "Hotkey", combo)

        self._mode_var = tk.StringVar(
            value="Hold to talk" if self.settings.get("hotkey_mode") == "hold"
            else "Press to start and stop")
        mode = ttk.Combobox(card, textvariable=self._mode_var, state="readonly",
                            values=["Hold to talk", "Press to start and stop"], width=30)
        self._row(card, "Mode", mode)

        self._lang_var = tk.StringVar(value=_label_for(LANGUAGES, self.settings.get("language")))
        lang = ttk.Combobox(card, textvariable=self._lang_var, state="readonly",
                            values=[l for l, _ in LANGUAGES], width=30)
        self._row(card, "Language", lang,
                  "Auto detect works well for English and Portuguese. "
                  "Pick Taglish when the team mixes Tagalog and English.")

        names = ["System default"] + [n for _, n in self._devices]
        current = self.settings.get("input_device")
        selected = "System default"
        for idx, name in self._devices:
            if idx == current:
                selected = name
        self._mic_var = tk.StringVar(value=selected)
        mic = ttk.Combobox(card, textvariable=self._mic_var, state="readonly",
                           values=names, width=30)
        self._row(card, "Microphone", mic)

    def _build_output(self, parent) -> None:
        card = self._card(parent, "Text")
        modes = {"paste": "Paste at the cursor", "type": "Type character by character",
                 "clipboard_only": "Copy to clipboard only"}
        self._insert_var = tk.StringVar(value=modes.get(self.settings.get("insert_mode"),
                                                        modes["paste"]))
        insert = ttk.Combobox(card, textvariable=self._insert_var, state="readonly",
                              values=list(modes.values()), width=30)
        self._row(card, "Insert", insert)
        self._insert_modes = modes

        self._check(card, "capitalize_first", "Capitalise the first word")
        self._check(card, "trailing_space", "Add a space at the end")
        self._check(card, "remove_fillers", "Remove filler sounds such as um and uh")
        self._check(card, "sounds", "Play a sound when recording starts and stops")
        self._check(card, "show_overlay", "Show the on-screen status pill")

        self._full(card, ttk.Label(
            card, text="Word replacements, one per line as spoken = written",
            style="Muted.TLabel"), pady=(8, 2))
        self._dict_text = tk.Text(card, height=3, width=40, font=("Consolas", 9),
                                  relief="solid", borderwidth=1, bg="#FFFFFF")
        self._full(card, self._dict_text)
        existing = self.settings.get("dictionary") or {}
        self._dict_text.insert(
            "1.0", "\n".join(k + " = " + v for k, v in existing.items()))

    def _build_advanced(self, parent) -> None:
        card = self._card(parent, "Engine")
        auto_label = "Automatic (picks the best for this computer)"
        values = [auto_label] + [l + "  -  " + size for l, _, size in MODEL_CATALOG]
        current = self.settings.get("model")
        selected = auto_label
        for idx, (label, model_id, size) in enumerate(MODEL_CATALOG):
            if model_id == current:
                selected = values[idx + 1]
        self._model_var = tk.StringVar(value=selected)
        self._model_values = values
        self._auto_label = auto_label
        model = ttk.Combobox(card, textvariable=self._model_var, state="readonly",
                             values=values, width=30)
        hint = ("This computer has an NVIDIA GPU, the large models will be fast."
                if cuda_available() else
                "No NVIDIA GPU found, the app will run on the processor. "
                "Small is the safe choice on older laptops.")
        self._row(card, "Model", model, hint)

        self._check(card, "save_recordings",
                    "Pilot mode: keep the audio and text of each dictation for accuracy testing")
        self._check(card, "launch_at_startup", "Start with Windows")
        self._vars["launch_at_startup"].set(startup.is_enabled())

        self._full(card, ttk.Label(
            card, text="Models download once and then run offline.",
            style="Muted.TLabel"), pady=(6, 0))

    # ---------- actions ----------

    def _save(self) -> None:
        values = {key: var.get() for key, var in self._vars.items()}

        values["hotkey"] = _value_for(HOTKEY_CHOICES, self._hotkey_var.get())
        values["hotkey_mode"] = "hold" if self._mode_var.get() == "Hold to talk" else "toggle"
        values["language"] = _value_for(LANGUAGES, self._lang_var.get())

        chosen_mic = self._mic_var.get()
        device = None
        for idx, name in self._devices:
            if name == chosen_mic:
                device = idx
        values["input_device"] = device

        for key, label in self._insert_modes.items():
            if label == self._insert_var.get():
                values["insert_mode"] = key

        chosen_model = self._model_var.get()
        if chosen_model == self._auto_label:
            values["model"] = "auto"
        else:
            index = self._model_values.index(chosen_model) - 1
            values["model"] = MODEL_CATALOG[index][1]

        values["dictionary"] = _parse_dictionary(self._dict_text.get("1.0", "end"))

        launch = values.pop("launch_at_startup", False)
        startup.set_enabled(bool(launch))
        values["launch_at_startup"] = bool(launch)

        self.settings.update(values)
        self.app.apply_settings()
        log.info("settings saved")
        self._close()

    def _close(self) -> None:
        SettingsWindow._open = None
        self.destroy()

    def _center(self, root) -> None:
        self.update_idletasks()
        w, h = self.winfo_width(), self.winfo_height()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        x = max(0, int(sw / 2 - w / 2))
        y = max(0, min(int(sh / 2 - h / 2), sh - h - 60))
        self.geometry("+" + str(x) + "+" + str(y))


def _icon_path():
    from .main import resource_path

    return resource_path("assets", "icon.ico")


def _label_for(pairs, value: str) -> str:
    for label, val in pairs:
        if val == value:
            return label
    return pairs[0][0]


def _value_for(pairs, label: str) -> str:
    for lab, val in pairs:
        if lab == label:
            return val
    return pairs[0][1]


def _parse_dictionary(raw: str) -> dict:
    result: dict = {}
    for line in raw.splitlines():
        if "=" not in line:
            continue
        spoken, _, written = line.partition("=")
        spoken, written = spoken.strip(), written.strip()
        if spoken and written:
            result[spoken] = written
    return result
