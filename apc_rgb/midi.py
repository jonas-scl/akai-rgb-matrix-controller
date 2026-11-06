"""MIDI output to the APC mini mk2.

Design rules (important when the controller is also used by a lighting desk
such as Onyx at the same time):

* Only ONE port is ever touched: the selected *output* port. Input ports are
  never opened, other devices are never opened.
* Only Note-On messages for the 64 pads (notes 0..63) are sent. Nothing else:
  no SysEx, no CC, no "all notes off", no reset.
* By default the port is only held open for a moment while sending and then
  released again, so that other programs can use it too (on Windows a MIDI
  port can only be opened by one program at a time).
* Closing the app/port sends nothing - the pads keep their colours as long as
  the controller has power.

All rtmidi calls run on one dedicated worker thread. On macOS rtmidi spins the
CoreMIDI run loop while listing ports; doing that on the Tk main thread makes
Tk callbacks run without the GIL and crashes Python.
"""

import re
from concurrent.futures import ThreadPoolExecutor

try:
    import rtmidi  # python-rtmidi
except Exception:  # pragma: no cover - missing backend
    rtmidi = None

RELEASE_DELAY_MS = 1500
CALL_TIMEOUT_S = 5


def normalize(name):
    """Port name without the running number Windows/rtmidi appends ('APC mini mk2 1')."""
    return re.sub(r"\s+\d+$", "", name or "").strip()


def apc_score(name):
    """How likely a port is the LED/control port of an APC mini mk2 (0 = not at all)."""
    n = name.lower()
    if "apc mini mk2" not in n and "apc mini mkii" not in n:
        return 0
    if any(bad in n for bad in ("midiin2", "midiout2", "notes", "port 2")):
        return 1
    if "control" in n:
        return 4
    if n.startswith("apc mini mk2"):
        return 3
    return 2


def pick_apc(names):
    scored = sorted(((apc_score(n), i) for i, n in enumerate(names)), reverse=True)
    if scored and scored[0][0] >= 2:
        return names[scored[0][1]]
    return None


class MidiLink:
    """Owns the single output port. All calls happen on the UI thread."""

    def __init__(self, scheduler=None, backend=None):
        # scheduler(ms, func) -> handle ; cancel via scheduler_cancel(handle)
        self._schedule = scheduler
        self._cancel = None
        self._release_job = None
        self._backend_factory = backend
        self._enum = None
        self._open_name = None
        self.target = None  # normalized port name we want to talk to
        self.release_port = True
        self.error = None          # None or "unavailable" / "not_found" / "busy" / "send_failed"
        self.error_detail = ""
        self.available = True
        self._worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="midi")
        self._init_enum()

    def set_scheduler(self, schedule, cancel):
        self._schedule = schedule
        self._cancel = cancel

    # -- backend -----------------------------------------------------------
    def _run(self, func, *args):
        """Run ``func`` on the MIDI thread and wait for its result."""
        return self._worker.submit(func, *args).result(timeout=CALL_TIMEOUT_S)

    def shutdown(self):
        """Close the port (sends nothing) and stop the MIDI thread."""
        self.close()
        self._worker.shutdown(wait=False)

    def _new_out(self):
        if self._backend_factory is not None:
            return self._backend_factory()
        if rtmidi is None:
            raise RuntimeError("python-rtmidi is not installed")
        return rtmidi.MidiOut(name="APC RGB Controller")

    def _init_enum(self):
        try:
            self._enum = self._run(self._new_out)
            self.available = True
        except Exception as exc:
            self._enum = None
            self.available = False
            self.error, self.error_detail = "unavailable", str(exc)

    # -- ports -------------------------------------------------------------
    def port_names(self):
        if self._enum is None:
            self._init_enum()
            if self._enum is None:
                return []
        try:
            return list(self._run(self._enum.get_ports))
        except Exception:
            return []

    def find_port(self, names=None):
        """Index and full name of the target port in the current port list."""
        if not self.target:
            return None, None
        names = self.port_names() if names is None else names
        for i, n in enumerate(names):
            if n == self.target or normalize(n) == self.target:
                return i, n
        return None, None

    def is_present(self, names=None):
        return self.find_port(names)[0] is not None

    def set_target(self, name):
        name = normalize(name) if name else None
        if name != self.target:
            self.close()
            self.target = name

    # -- open / close ------------------------------------------------------
    def _ensure_open(self):
        if self._open_name is not None:
            return True
        index, full = self.find_port()
        if index is None:
            self.error, self.error_detail = "not_found", ""
            return False
        try:
            # The same rtmidi object is used for listing and sending, so no
            # extra MIDI clients are created for every send.
            self._run(self._enum.open_port, index)
        except Exception as exc:
            self.error, self.error_detail = "busy", str(exc)
            self._reset_backend()
            return False
        self._open_name = full
        return True

    def _reset_backend(self):
        try:
            if self._enum is not None:
                self._run(self._enum.close_port)
                self._run(self._enum.delete)
        except Exception:
            pass
        self._enum = None
        self._init_enum()

    def close(self):
        """Close the port. Sends nothing (pads keep their colours)."""
        self._cancel_release()
        if self._open_name is not None:
            self._open_name = None
            try:
                self._run(self._enum.close_port)
            except Exception:
                self._reset_backend()

    def is_open(self):
        return self._open_name is not None

    def _cancel_release(self):
        if self._release_job is not None and self._cancel is not None:
            try:
                self._cancel(self._release_job)
            except Exception:
                pass
        self._release_job = None

    def _schedule_release(self):
        self._cancel_release()
        if not self.release_port:
            return
        if self._schedule is None:
            self.close()
        else:
            self._release_job = self._schedule(RELEASE_DELAY_MS, self._release)

    def _release(self):
        self._release_job = None
        self.close()

    # -- sending -----------------------------------------------------------
    def send_pads(self, items):
        """Send ``[(note, velocity, channel), ...]``. Returns True on success."""
        items = [(n, v, c) for n, v, c in items if 0 <= n <= 63]
        if not items:
            return True
        if not self._ensure_open():
            return False
        out = self._enum

        def send_all():
            for note, vel, ch in items:
                out.send_message([0x90 | (ch & 0x0F), note & 0x7F, vel & 0x7F])

        try:
            self._run(send_all)
        except Exception as exc:
            self.error, self.error_detail = "send_failed", str(exc)
            self.close()
            return False
        self.error = None
        self._schedule_release()
        return True
