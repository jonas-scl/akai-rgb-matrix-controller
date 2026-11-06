"""Pad layouts and the .midirgb file format.

A layout is a tuple of 64 ``(velocity, mode)`` pairs, indexed by pad note
(0 = bottom left, 63 = top right).

File format v2 (JSON)::

    {
      "format": "midirgb",
      "version": 2,
      "name": "Mein Layout",
      "saved": "2026-11-05T20:15:00",
      "pads": [ {"note": 0, "velocity": 5, "channel": 6, "hex": "#FF0000"}, ... ]
    }

v1 files (``{"0": {"color": "#FF0000", "channel": 6, "device": "..."}, ...}``)
are still read.
"""

import json
import os
import tempfile
from datetime import datetime

from .palette import DEFAULT_MODE, HEX_TO_VELOCITY, VELOCITY_HEX

PAD_COUNT = 64
EXTENSION = ".midirgb"


def empty_layout():
    return tuple((0, DEFAULT_MODE) for _ in range(PAD_COUNT))


def _clamp(value, lo, hi, default):
    try:
        value = int(value)
    except (TypeError, ValueError):
        return default
    return value if lo <= value <= hi else default


def parse(data):
    """Return ``(pads, name)`` from decoded JSON data (v1 or v2)."""
    pads = list(empty_layout())
    name = data.get("name") if isinstance(data, dict) else None
    if isinstance(data, dict) and isinstance(data.get("pads"), list):
        for entry in data["pads"]:
            if not isinstance(entry, dict):
                continue
            note = _clamp(entry.get("note"), 0, PAD_COUNT - 1, None)
            if note is None:
                continue
            if "velocity" in entry:
                vel = _clamp(entry.get("velocity"), 0, 127, 0)
            else:
                vel = HEX_TO_VELOCITY.get(str(entry.get("hex", "")).upper(), 0)
            pads[note] = (vel, _clamp(entry.get("channel"), 0, 15, DEFAULT_MODE))
    elif isinstance(data, dict):
        found = False
        for key, entry in data.items():
            note = _clamp(key, 0, PAD_COUNT - 1, None)
            if note is None or not isinstance(entry, dict):
                continue
            found = True
            if "velocity" in entry:
                vel = _clamp(entry.get("velocity"), 0, 127, 0)
            else:
                vel = HEX_TO_VELOCITY.get(str(entry.get("color", "")).upper(), 0)
            pads[note] = (vel, _clamp(entry.get("channel"), 0, 15, DEFAULT_MODE))
        if not found:
            raise ValueError("No pad data found")
    else:
        raise ValueError("Unknown file format")
    return tuple(pads), (name if isinstance(name, str) else None)


def load_file(path):
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    pads, name = parse(data)
    if not name:
        name = os.path.splitext(os.path.basename(path))[0]
    return pads, name


def to_data(pads, name=None):
    return {
        "format": "midirgb",
        "version": 2,
        "name": name or "",
        "saved": datetime.now().isoformat(timespec="seconds"),
        "pads": [
            {"note": i, "velocity": vel, "channel": mode, "hex": VELOCITY_HEX[vel]}
            for i, (vel, mode) in enumerate(pads)
        ],
    }


def write_json_atomic(path, data):
    """Write JSON so that a crash never leaves a half-written file behind."""
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", suffix=".json", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=1, ensure_ascii=False)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def save_file(path, pads, name=None):
    write_json_atomic(path, to_data(pads, name))
