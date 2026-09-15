"""Settings window."""
from __future__ import annotations

import logging
import tkinter as tk
from tkinter import ttk

from . import audio
from .config import APP_NAME, data_dir
from .hotkey import HOTKEY_CHOICES, describe
from .platform_support import (IS_MAC, input_monitoring_ready,
                               installed_properly, is_translocated,
                               open_accessibility_settings,
                               open_applications_folder, open_folder,
                               play_tone, prime_keyboard_layout,
                               request_accessibility, set_startup,
                               startup_enabled)
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
# The permission window watches for the grant instead of asking the user to
# come back and click something.
PERMISSION_POLL_MS = 1000
# Long enough to read the confirmation, short enough that nobody is left
# wondering whether the window is stuck again.
PERMISSION_CLOSE_MS = 2500


def _configure_styles(widget) -> None:
    """The look shared by every window in the app."""
    style = ttk.Style(widget)
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
        if not IS_MAC:
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
        _configure_styles(self)

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
                   command=lambda: open_folder(data_dir())).pack(side="left")

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

        volume = tk.Frame(card, bg="#FFFFFF")
        initial = float(self.settings.get("sound_volume") or 20)
        # DoubleVar, and the callback only writes to the label. Writing back to
        # the variable from here fights the widget while it is being laid out.
        self._volume_var = tk.DoubleVar(value=initial)
        readout = ttk.Label(volume, text=str(int(initial)) + "%",
                            style="Card.TLabel", width=5)
        scale = ttk.Scale(
            volume, from_=0, to=100, orient="horizontal",
            variable=self._volume_var,
            command=lambda v: readout.configure(text=str(int(float(v))) + "%"),
        )
        scale.pack(side="left", fill="x", expand=True)
        readout.pack(side="left", padx=(10, 0))
        ttk.Button(volume, text="Test", style="Ghost.TButton",
                   command=self._test_sound).pack(side="left", padx=(8, 0))
        # The scale settles its geometry after the first idle pass, so the
        # stored value is applied once that is done.
        self.after_idle(lambda: (self._volume_var.set(initial),
                                 readout.configure(text=str(int(initial)) + "%")))
        self._row(card, "Sound volume", volume)
        self._check(card, "show_overlay", "Show the on-screen status pill")

        self._full(card, ttk.Label(
            card, text="Word replacements, one per line as spoken = written",
            style="Muted.TLabel"), pady=(8, 2))
        self._dict_text = tk.Text(card, height=3, width=40, font=("Consolas", 9),
                                  relief="solid", borderwidth=1, bg="#FFFFFF")
        self._full(card, self._dict_text)

        self._check(card, "keep_history_text",
                    "Keep the text of the last 20 dictations, for support")
        history_row = tk.Frame(card, bg="#FFFFFF")
        self._history_note = ttk.Label(history_row, text="", style="Muted.TLabel")
        ttk.Button(history_row, text="Clear history", style="Ghost.TButton",
                   command=self._clear_history).pack(side="left")
        self._history_note.pack(side="left", padx=(10, 0))
        self._full(card, history_row, pady=(6, 2))
        self._show_history_count()
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
        if cuda_available():
            hint = "This computer has an NVIDIA GPU, the large models will be fast."
        elif IS_MAC:
            hint = ("Runs on the processor. Apple Silicon handles Small and Turbo "
                    "comfortably, older Intel Macs should stay on Small.")
        else:
            hint = ("No NVIDIA GPU found, the app will run on the processor. "
                    "Small is the safe choice on older laptops.")
        self._row(card, "Model", model, hint)

        self._check(card, "save_recordings",
                    "Pilot mode: keep the audio and text of each dictation for accuracy testing")
        self._check(card, "launch_at_startup",
                    "Start at login" if IS_MAC else "Start with Windows")
        self._vars["launch_at_startup"].set(startup_enabled())

        self._full(card, ttk.Label(
            card, text="Models download once and then run offline.",
            style="Muted.TLabel"), pady=(6, 0))

    # ---------- actions ----------

    def _show_history_count(self) -> None:
        from .main import data_dir as _dd  # same folder the app writes to

        path = data_dir() / "history.jsonl"
        try:
            count = len([l for l in path.read_text(encoding="utf-8").splitlines() if l.strip()])
        except (OSError, UnicodeDecodeError):
            count = 0
        self._history_note.configure(
            text=(str(count) + " stored") if count else "nothing stored")

    def _clear_history(self) -> None:
        from tkinter import messagebox

        from .main import clear_history

        if not messagebox.askyesno(
            "Clear history",
            "Remove every stored transcript from this computer?\n\n"
            "This cannot be undone.",
            parent=self,
        ):
            return
        removed = clear_history()
        log.info("history cleared, %d entries removed", removed)
        self._show_history_count()
        self.app.last_text = ""

    def _test_sound(self) -> None:
        """Plays the stop tone at the level the slider is showing."""
        play_tone("stop", int(round(float(self._volume_var.get()))))


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

        values["sound_volume"] = int(round(float(self._volume_var.get())))
        values["dictionary"] = _parse_dictionary(self._dict_text.get("1.0", "end"))

        launch = values.pop("launch_at_startup", False)
        set_startup(bool(launch))
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


class PermissionWindow(tk.Toplevel):
    """Asks for the macOS permission the dictation key depends on.

    Without it pynput starts, listens, and never hears a thing, so the app
    looks perfectly healthy while doing nothing. This is the only screen that
    explains why.
    """

    _open: "PermissionWindow | None" = None

    def __init__(self, root: tk.Tk, app) -> None:
        if PermissionWindow._open is not None:
            try:
                PermissionWindow._open.lift()
                PermissionWindow._open.focus_force()
                return
            except tk.TclError:
                PermissionWindow._open = None
        super().__init__(root)
        PermissionWindow._open = self
        self.app = app
        self._poll_id = None
        self._done = False

        self.title(APP_NAME + " needs permission")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self._close)
        self._build()
        self._center()
        self.lift()
        self.focus_force()
        self._poll()

    def _misplaced(self) -> bool:
        """True when where the app sits is the reason a grant will not hold."""
        return is_translocated() or not installed_properly()

    def _build(self) -> None:
        _configure_styles(self)
        header = tk.Frame(self, bg=NAVY, padx=20, pady=12)
        header.pack(fill="x")
        self._headline = tk.Label(header, text="One permission to go", bg=NAVY,
                                  fg="#FFFFFF", font=("Segoe UI", 15, "bold"))
        self._headline.pack(anchor="w")
        self._subhead = tk.Label(
            header, text="macOS keeps the keyboard private until you say otherwise.",
            bg=NAVY, fg="#C8D2E2", font=("Segoe UI", 9))
        self._subhead.pack(anchor="w")

        body = tk.Frame(self, bg=BG, padx=20, pady=16)
        body.pack(fill="both", expand=True)

        if self._misplaced():
            explain = ("Coconut Whisper is running from the folder it was "
                       "unzipped into. macOS hands an app opened from there a "
                       "fresh temporary location on every launch, and it files "
                       "the permission against that location, so whatever you "
                       "allow is gone by the next time you open it.")
            steps = chr(10).join((
                "1.  Quit Coconut Whisper from the menu bar.",
                "2.  Drag Coconut Whisper into your Applications folder.",
                "3.  Open it from there, and the permission will hold.",
            ))
        else:
            explain = ("Coconut Whisper watches for the dictation key, and "
                       "macOS calls that Accessibility. Until it is allowed, "
                       "holding the key does nothing at all. Every new version "
                       "counts as a different app to macOS, so an entry left "
                       "over from the previous one has to go first.")
            steps = chr(10).join((
                "1.  Open System Settings, Privacy and Security, Accessibility.",
                "2.  If Coconut Whisper is already in the list, select it and "
                "remove it with the minus button.",
                "3.  Come back here and click Ask macOS.",
            ))
        self._explain = tk.Label(body, text=explain,
                                 bg=BG, fg=FG, font=("Segoe UI", 10),
                                 wraplength=440, justify="left")
        self._explain.pack(anchor="w")
        self._steps = tk.Label(body, text=steps, bg="#FFFFFF", fg=FG,
                               font=("Segoe UI", 10), justify="left",
                               padx=14, pady=12)
        self._steps.pack(fill="x", pady=(12, 4))

        self._status = tk.Label(body, text="", bg=BG, fg=FG_MUTED,
                                font=("Segoe UI", 9), wraplength=440,
                                justify="left")
        self._status.pack(anchor="w", pady=(6, 0))

        footer = tk.Frame(self, bg=BG, padx=20, pady=14)
        footer.pack(fill="x")
        self._footer = footer
        if self._misplaced():
            ttk.Button(footer, text="Open Applications folder",
                       style="Accent.TButton",
                       command=open_applications_folder).pack(side="right")
        else:
            ttk.Button(footer, text="Ask macOS", style="Accent.TButton",
                       command=self._request).pack(side="right")
            ttk.Button(footer, text="Open System Settings", style="Ghost.TButton",
                       command=self._open_settings).pack(side="right", padx=(0, 8))
        ttk.Button(footer, text="Later", style="Ghost.TButton",
                   command=self._close).pack(side="left")

    def _open_settings(self) -> None:
        open_accessibility_settings()
        self._status.configure(
            text="System Settings is open. Switch Coconut Whisper on, then come "
                 "back and click Check again.")

    def _request(self) -> None:
        """Asks macOS to list us, which is the step people cannot find."""
        if request_accessibility():
            self._granted()
            return
        self._status.configure(
            text="Not allowed yet. macOS shows its dialog once per version, "
                 "so if nothing appeared, remove the old Coconut Whisper "
                 "entry in Accessibility and click here again.")

    def _poll(self) -> None:
        """Watches for the grant so nobody has to come back and click.

        Runs on the interface thread, the only one allowed to talk to Tk.
        """
        if self._done:
            return
        if input_monitoring_ready():
            self._granted()
            return
        try:
            self._poll_id = self.after(PERMISSION_POLL_MS, self._poll)
        except tk.TclError:
            self._poll_id = None

    def _granted(self) -> None:
        if self._done:
            return
        self._done = True
        self._cancel_poll()
        # The answer takes over the whole window, before anything else runs.
        # Rebuilding the listener reaches into the system, and if that fails
        # the user still has to see that the permission went through. Leaving
        # the old heading and the old steps up while a small grey line below
        # claimed success is how a working app read as a broken one.
        self._celebrate()
        # Reading the layout again here picks up an input source changed
        # while the app was waiting, and does it on the interface thread.
        prime_keyboard_layout()
        # The tap is built when the listener starts, so it has to be rebuilt
        # now that the permission exists.
        try:
            self.app.listener.restart()
        except Exception:
            log.exception("the listener did not come back after the grant")
            return
        log.info("accessibility permission granted, listener restarted")

    def _celebrate(self) -> None:
        """Turns the whole window into the answer, then shows itself out."""
        try:
            key = describe(self.app.settings.get("hotkey"))
        except Exception:
            key = "the dictation key"
        try:
            self.title(APP_NAME + " is ready")
            self._headline.configure(text="That did it")
            self._subhead.configure(
                text="Coconut Whisper can see the dictation key now.")
            self._explain.configure(
                text="Click into any text box, hold " + key + " and talk. Let go "
                     "when you are done and the text appears where the cursor is. "
                     "This window closes on its own.")
            # Destroyed, not just unpacked: nothing that contradicts the
            # answer should survive anywhere in this window.
            self._steps.destroy()
            self._status.configure(text="")
            for child in self._footer.winfo_children():
                child.destroy()
            ttk.Button(self._footer, text="Close", style="Accent.TButton",
                       command=self._close).pack(side="right")
            self.update_idletasks()
            self.after(PERMISSION_CLOSE_MS, self._close)
        except tk.TclError:
            log.debug("the permission window went away mid celebration",
                      exc_info=True)

    def _cancel_poll(self) -> None:
        if self._poll_id is not None:
            try:
                self.after_cancel(self._poll_id)
            except tk.TclError:
                pass
            self._poll_id = None

    def _close(self) -> None:
        self._cancel_poll()
        self._done = True
        PermissionWindow._open = None
        # The window closes itself after a grant, so a button press or a
        # caller doing the same must not land on an already dead widget.
        try:
            self.destroy()
        except tk.TclError:
            pass

    def _center(self) -> None:
        self.update_idletasks()
        w, h = self.winfo_width(), self.winfo_height()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry("+" + str(max(0, int(sw / 2 - w / 2)))
                      + "+" + str(max(0, int(sh / 3 - h / 2))))


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
