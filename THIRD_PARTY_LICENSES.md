# Third-party licenses

The APC RGB Controller uses the following third-party components. They are **not** covered by the
project's own [LICENSE](LICENSE); each keeps its own license. All of them allow use and
redistribution (also in closed or commercial software) as long as their copyright and license
notices are kept.

| Component | Used for | License |
| --- | --- | --- |
| [Python](https://www.python.org) | runtime (bundled in the builds) | PSF License |
| [Tcl/Tk](https://www.tcl.tk) (via `tkinter`) | windows and drawing (bundled) | Tcl/Tk license (BSD-style) |
| [python-rtmidi](https://github.com/SpotlightKid/python-rtmidi) incl. [RtMidi](https://github.com/thestk/rtmidi) | MIDI output | MIT / RtMidi license (modified MIT) |
| [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) | user interface | MIT |
| [darkdetect](https://github.com/albertosottile/darkdetect) | dependency of CustomTkinter | BSD-3-Clause |
| [packaging](https://github.com/pypa/packaging) | dependency of CustomTkinter | Apache-2.0 or BSD-2-Clause |
| Roboto font (bundled with CustomTkinter) | font on Windows | Apache-2.0 |
| [PyInstaller](https://pyinstaller.org) bootloader | building the executables | GPL-2.0+ with bootloader exception (allows any license for the built app) |

Only used during development and the build, not bundled: PyInstaller itself, Pillow (icon
conversion), pytest.

The full license texts are collected automatically during every build
(`tools/third_party_notices.py`) into `THIRD_PARTY_NOTICES.txt`. That file is bundled inside the
app (••• menu → “Licenses …”) and attached to every release.
