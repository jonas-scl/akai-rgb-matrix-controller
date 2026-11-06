"""Collect the license texts of all third-party components that end up in the app builds.

    python tools/third_party_notices.py OUT.txt

Run with the same Python environment that is used for the PyInstaller build.
"""

import glob
import os
import sys
import tkinter
from importlib import metadata

HERE = os.path.dirname(os.path.abspath(__file__))
PACKAGES = [
    ("python-rtmidi", "python-rtmidi (MIDI output, includes RtMidi)"),
    ("customtkinter", "CustomTkinter (user interface)"),
    ("darkdetect", "darkdetect (dependency of CustomTkinter)"),
    ("packaging", "packaging (dependency of CustomTkinter)"),
]


def package_license(dist):
    files = [f for f in (metadata.files(dist) or [])
             if os.path.basename(str(f)).upper().startswith(("LICEN", "COPYING"))
             and ".dist-info" in str(f)]
    texts = []
    for f in files:
        try:
            texts.append(f.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            continue
    if not texts:
        raise SystemExit("No license file found for " + dist)
    return metadata.version(dist), "\n\n".join(texts)


def python_license():
    candidates = [os.path.join(sys.base_prefix, "LICENSE.txt"),
                  os.path.join(sys.base_prefix, "LICENSE")]
    candidates += glob.glob(os.path.join(sys.base_prefix, "lib", "python3*", "LICENSE.txt"))
    candidates += glob.glob(os.path.join(sys.base_prefix, "Lib", "LICENSE.txt"))
    for path in candidates:
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as fh:
                return fh.read()
    raise SystemExit("Python LICENSE.txt not found")


def tcl_tk_licenses():
    """Tcl/Tk license: from the Python installation if present, otherwise the bundled copy."""
    tcl_lib = tkinter.Tcl().eval("info library")
    root = os.path.dirname(tcl_lib)
    for pattern in ("tcl8*/license.terms", "tk8*/license.terms", "tk8*/demos/license.terms"):
        for path in sorted(glob.glob(os.path.join(root, pattern))):
            with open(path, encoding="utf-8", errors="replace") as fh:
                return fh.read()
    with open(os.path.join(HERE, "licenses", "tcl-tk-license.terms"), encoding="utf-8") as fh:
        return fh.read()


def main(out):
    parts = ["THIRD-PARTY NOTICES - APC RGB Controller\n",
             "This application bundles the following third-party software. Each component is\n"
             "licensed under its own license, reproduced below. The license of the APC RGB\n"
             "Controller itself (LICENSE) does not apply to these components.\n"]

    def section(title, text):
        parts.append("\n" + "=" * 78 + "\n" + title + "\n" + "=" * 78 + "\n\n" + text.strip() + "\n")

    section("Python %d.%d.%d (Python Software Foundation License)" % sys.version_info[:3], python_license())
    section("Tcl/Tk %s (Tcl/Tk license)" % tkinter.TkVersion, tcl_tk_licenses())
    for dist, title in PACKAGES:
        version, text = package_license(dist)
        section("%s %s" % (title, version), text)
    section("Roboto font (bundled with CustomTkinter) - Copyright Google LLC, Apache License 2.0",
            "The Roboto font is licensed under the Apache License, Version 2.0.\n"
            "The full license text is included in the 'packaging' section above\n"
            "(LICENSE.APACHE) and at https://www.apache.org/licenses/LICENSE-2.0")
    section("PyInstaller bootloader",
            "The executable was created with PyInstaller (https://pyinstaller.org).\n"
            "The PyInstaller bootloader is licensed under the GNU General Public License v2\n"
            "or later with a special exception that allows it to be used in executables of\n"
            "any license.")

    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("".join(parts))
    print("wrote", out)


if __name__ == "__main__":
    main(sys.argv[1])
