"""Run-at-login registration (per user, no admin rights needed)."""
from __future__ import annotations

import logging
import sys
import winreg

from .config import APP_NAME

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "CoconutWhisper"

log = logging.getLogger(__name__)


def _command() -> str:
    if getattr(sys, "frozen", False):
        return '"' + sys.executable + '"'
    return '"' + sys.executable + '" -m app.main'


def is_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, VALUE_NAME)
            return True
    except OSError:
        return False


def set_enabled(enabled: bool) -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, _command())
            else:
                try:
                    winreg.DeleteValue(key, VALUE_NAME)
                except FileNotFoundError:
                    pass
        return True
    except OSError:
        log.exception("could not update the %s startup entry", APP_NAME)
        return False
