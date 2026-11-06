import json
import os

import pytest

from apc_rgb.layout import empty_layout, load_file, parse, save_file
from apc_rgb.midi import MidiLink, normalize, pick_apc
from apc_rgb.palette import VELOCITY_HEX
from apc_rgb.storage import PRESET_DIR, Storage


def test_builtin_presets_are_v1_files_and_load():
    for name in ("standard", "colours"):
        path = os.path.join(PRESET_DIR, name + ".midirgb")
        with open(path, encoding="utf-8") as fh:
            raw = json.load(fh)
        pads, _ = load_file(path)
        assert len(pads) == 64
        # every pad in the original file maps to a known velocity
        for key, entry in raw.items():
            vel, ch = pads[int(key)]
            assert entry["color"] == "#000000" or vel != 0
            assert ch == entry["channel"]


def test_v1_colour_mapping():
    pads, _ = parse({"0": {"color": "#0000FF", "channel": 10, "device": "x"},
                     "63": {"color": "#8b00ff", "channel": 6}})
    assert pads[0] == (45, 10)
    assert pads[63] == (52, 6)
    assert pads[1] == (0, 6)


def test_v2_roundtrip(tmp_path):
    pads = list(empty_layout())
    pads[5] = (127, 15)
    pads[60] = (3, 0)
    path = tmp_path / "x.midirgb"
    save_file(str(path), tuple(pads), "Test")
    loaded, name = load_file(str(path))
    assert loaded == tuple(pads)
    assert name == "Test"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["version"] == 2 and data["pads"][5]["hex"] == VELOCITY_HEX[127]


def test_parse_rejects_garbage():
    with pytest.raises(ValueError):
        parse({"foo": "bar"})
    with pytest.raises(ValueError):
        parse([1, 2, 3])


def test_storage_standard_library_history(tmp_path):
    st = Storage(str(tmp_path))
    builtin = st.load_standard()
    assert not st.has_custom_standard()
    custom = tuple((21, 6) for _ in range(64))
    st.save_standard(custom)
    assert st.load_standard() == custom
    st.reset_standard()
    assert st.load_standard() == builtin

    st.save_to_library("Show A/B", custom)
    lib = st.library()
    assert [it.name for it in lib] == ["Show A/B"]
    st.rename_in_library(lib[0], "Show C")
    assert [it.name for it in st.library()] == ["Show C"]

    assert st.push_history(builtin, "Standard")
    assert st.push_history(custom, "Grün")
    assert st.push_history(builtin, "Standard")  # moves to top, no duplicate
    assert [h["name"] for h in st.history] == ["Standard", "Grün"]
    assert not st.push_history(empty_layout())  # all-off layouts are not remembered
    assert [h["pads"] for h in Storage(str(tmp_path)).history] == [builtin, custom]

    st.save_current(custom, "Grün")
    assert Storage(str(tmp_path)).load_current() == (custom, "Grün")


def test_port_matching():
    assert normalize("APC mini mk2 1") == "APC mini mk2"
    assert normalize("APC mini mk2") == "APC mini mk2"
    win = ["Microsoft GS Wavetable Synth 0", "APC mini mk2 1", "MIDIOUT2 (APC mini mk2) 2"]
    assert pick_apc(win) == "APC mini mk2 1"
    mac = ["APC mini mk2 Notes", "APC mini mk2 Control"]
    assert pick_apc(mac) == "APC mini mk2 Control"
    assert pick_apc(["IAC Driver Bus 1"]) is None


class FakeOut:
    log = []
    ports = ["Microsoft GS Wavetable Synth 0", "APC mini mk2 1", "MIDIOUT2 (APC mini mk2) 2"]
    busy = False

    def get_ports(self):
        return list(self.ports)

    def open_port(self, i):
        if FakeOut.busy:
            raise RuntimeError("busy")
        self.idx = i
        FakeOut.log.append(("open", self.ports[i]))

    def close_port(self):
        FakeOut.log.append(("close",))

    def delete(self):
        pass

    def send_message(self, msg):
        FakeOut.log.append(("msg", self.ports[self.idx], tuple(msg)))


def test_midi_only_touches_target_port_and_note_on():
    FakeOut.log = []
    link = MidiLink(backend=FakeOut)  # no scheduler -> releases immediately
    link.set_target("APC mini mk2 3")  # Windows renumbered the port
    assert link.send_pads([(0, 5, 6), (63, 45, 10), (100, 1, 0)])  # note 100 is ignored
    assert FakeOut.log == [("open", "APC mini mk2 1"),
                           ("msg", "APC mini mk2 1", (0x96, 0, 5)),
                           ("msg", "APC mini mk2 1", (0x9A, 63, 45)),
                           ("close",)]
    # closing sends nothing
    FakeOut.log = []
    link.close()
    assert FakeOut.log == []


def test_midi_busy_port_reports_error():
    FakeOut.busy = True
    try:
        link = MidiLink(backend=FakeOut)
        link.set_target("APC mini mk2")
        assert not link.send_pads([(0, 5, 6)])
        assert link.error
    finally:
        FakeOut.busy = False


def test_translations_complete():
    import string

    from apc_rgb.i18n import COLOUR_NAMES, S, colour_name, set_language, t

    fields = lambda text: sorted(f for _, f, _, _ in string.Formatter().parse(text) if f)  # noqa: E731
    for key, (en, de) in S.items():
        assert en and de, key
        if key != "date_fmt":
            assert fields(en) == fields(de), key
    assert all(len(v) == 2 for v in COLOUR_NAMES.values())
    set_language("de")
    assert t("marked_many", n=3) == "3 Pads markiert" and colour_name(45) == "Blau"
    set_language("en")
    assert colour_name(45) == "Blue" and colour_name(100) == "Colour 100"
