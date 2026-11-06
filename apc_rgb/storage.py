"""Where everything is kept on disk.

All user data lives in one folder:

* Windows: ``%APPDATA%\\APC RGB Controller``
* macOS:   ``~/Library/Application Support/APC RGB Controller``
* Linux:   ``~/.config/apc-rgb-controller``

Contents::

    settings.json        device, options, window size
    current.midirgb      autosave of the current pads (written on every change)
    standard.midirgb     your own "Standard" layout (falls back to the built-in one)
    history.json         recently used layouts
    layouts/*.midirgb    your saved layouts
"""

import json
import os
import re
import sys
from datetime import datetime

from . import APP_NAME
from .layout import EXTENSION, load_file, parse, save_file, write_json_atomic

PRESET_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "presets")
HISTORY_LIMIT = 20


def default_data_dir():
    override = os.environ.get("APC_RGB_DATA_DIR")
    if override:
        return override
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        return os.path.join(base, APP_NAME)
    if sys.platform == "darwin":
        return os.path.join(os.path.expanduser("~/Library/Application Support"), APP_NAME)
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "apc-rgb-controller")


def _safe_filename(name):
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", name).strip(" .")
    return (name or "Layout")[:80]


class LibraryItem:
    def __init__(self, path, name, pads, mtime):
        self.path = path
        self.name = name
        self.pads = pads
        self.mtime = mtime


class Storage:
    def __init__(self, data_dir=None):
        self.dir = data_dir or default_data_dir()
        self.layouts_dir = os.path.join(self.dir, "layouts")
        os.makedirs(self.layouts_dir, exist_ok=True)
        self._settings_path = os.path.join(self.dir, "settings.json")
        self._current_path = os.path.join(self.dir, "current" + EXTENSION)
        self._standard_path = os.path.join(self.dir, "standard" + EXTENSION)
        self._history_path = os.path.join(self.dir, "history.json")
        self.settings = self._read_json(self._settings_path, {})
        if not isinstance(self.settings, dict):
            self.settings = {}
        self.history = self._load_history()

    # -- helpers -----------------------------------------------------------
    @staticmethod
    def _read_json(path, default):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, ValueError):
            return default

    # -- settings ----------------------------------------------------------
    def get(self, key, default=None):
        return self.settings.get(key, default)

    def set(self, key, value):
        self.settings[key] = value
        self.save_settings()

    def save_settings(self):
        try:
            write_json_atomic(self._settings_path, self.settings)
        except OSError:
            pass

    # -- autosave ----------------------------------------------------------
    def load_current(self):
        try:
            return load_file(self._current_path)
        except (OSError, ValueError):
            return None

    def save_current(self, pads, name=None):
        save_file(self._current_path, pads, name)

    # -- presets -----------------------------------------------------------
    @staticmethod
    def builtin(name):
        return load_file(os.path.join(PRESET_DIR, name + EXTENSION))[0]

    def has_custom_standard(self):
        return os.path.exists(self._standard_path)

    def load_standard(self):
        if self.has_custom_standard():
            try:
                return load_file(self._standard_path)[0]
            except (OSError, ValueError):
                pass
        return self.builtin("standard")

    def save_standard(self, pads):
        save_file(self._standard_path, pads, "Standard")

    def reset_standard(self):
        try:
            os.remove(self._standard_path)
        except OSError:
            pass

    def load_colour_test(self):
        return self.builtin("colours")

    # -- library -----------------------------------------------------------
    def library(self):
        items = []
        try:
            names = os.listdir(self.layouts_dir)
        except OSError:
            return items
        for fn in names:
            if not fn.lower().endswith(EXTENSION) or fn.startswith("."):
                continue
            path = os.path.join(self.layouts_dir, fn)
            try:
                pads, name = load_file(path)
                mtime = os.path.getmtime(path)
            except (OSError, ValueError):
                continue
            items.append(LibraryItem(path, name, pads, mtime))
        items.sort(key=lambda it: it.name.lower())
        return items

    def library_path(self, name):
        return os.path.join(self.layouts_dir, _safe_filename(name) + EXTENSION)

    def save_to_library(self, name, pads):
        path = self.library_path(name)
        save_file(path, pads, name)
        return path

    def rename_in_library(self, item, new_name):
        new_path = self.library_path(new_name)
        save_file(new_path, item.pads, new_name)
        if os.path.normcase(os.path.abspath(new_path)) != os.path.normcase(os.path.abspath(item.path)):
            try:
                os.remove(item.path)
            except OSError:
                pass
        return new_path

    @staticmethod
    def delete_from_library(item):
        os.remove(item.path)

    # -- history -----------------------------------------------------------
    def _load_history(self):
        raw = self._read_json(self._history_path, [])
        history = []
        if isinstance(raw, list):
            for entry in raw:
                try:
                    pads, _ = parse({"pads": entry["pads"]})
                    history.append({"pads": pads, "name": str(entry.get("name") or ""),
                                    "time": str(entry.get("time") or "")})
                except (KeyError, TypeError, ValueError):
                    continue
        return history[:HISTORY_LIMIT]

    def push_history(self, pads, name=""):
        """Remember a layout as 'recently used' (newest first, no duplicates)."""
        if all(vel == 0 for vel, _ in pads):
            return False
        self.history = [h for h in self.history if h["pads"] != pads]
        self.history.insert(0, {"pads": pads, "name": name or "",
                                "time": datetime.now().isoformat(timespec="seconds")})
        del self.history[HISTORY_LIMIT:]
        self._save_history()
        return True

    def remove_history(self, index):
        if 0 <= index < len(self.history):
            del self.history[index]
            self._save_history()

    def clear_history(self):
        self.history = []
        self._save_history()

    def _save_history(self):
        data = [{"name": h["name"], "time": h["time"],
                 "pads": [{"note": i, "velocity": v, "channel": m} for i, (v, m) in enumerate(h["pads"])]}
                for h in self.history]
        try:
            write_json_atomic(self._history_path, data)
        except OSError:
            pass
