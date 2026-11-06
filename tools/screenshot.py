"""Helpers for the README screenshot taken in CI (macOS).

    python tools/screenshot.py prepare DATA_DIR      # demo layouts, history, settings
    python tools/screenshot.py crop DATA_DIR IN.png OUT.png
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def prepare(data_dir):
    from apc_rgb.storage import Storage

    st = Storage(data_dir)
    test = st.load_colour_test()
    standard = st.load_standard()
    st.save_to_library("Friday concert", tuple((v, 9 if i % 8 == 0 else m) for i, (v, m) in enumerate(test)))
    st.save_to_library("Theatre", tuple((44 if v == 45 else v, m) for v, m in standard))
    st.push_history(tuple((v, 2) for v, m in test), "Colour test")
    st.push_history(test, "Colour test")
    st.save_current(standard, "Default")
    st.settings.update({"geometry": "1240x800+40+60", "base_name": "Default", "base_clean": True, "language": "en",
                        "color": 45, "mode": 6})
    st.save_settings()


def crop(data_dir, src, dst):
    from PIL import Image

    with open(os.path.join(data_dir, "window.json"), encoding="utf-8") as fh:
        win = json.load(fh)
    img = Image.open(src)
    scale = img.width / float(win["screen_w"])
    box = tuple(round(v * scale) for v in (win["x"], win["y"], win["x"] + win["w"], win["y"] + win["h"]))
    img.crop(box).convert("RGB").save(dst, optimize=True)
    print("cropped", box, "scale", scale)


if __name__ == "__main__":
    if sys.argv[1] == "prepare":
        prepare(sys.argv[2])
    else:
        crop(*sys.argv[2:5])
