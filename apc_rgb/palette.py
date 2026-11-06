"""Colours and LED modes of the Akai APC mini mk2.

The pad LEDs are controlled with plain Note-On messages:

* note      = pad number (0 = bottom left, 63 = top right)
* velocity  = colour index (0..127, see ``VELOCITY_HEX``)
* channel   = brightness / behaviour (see ``MODES``)
"""

# Display colour for each of the 128 velocity values (APC mini mk2 colour table).
_TABLE = """
000000 1E1E1E 7F7F7F FFFFFF FF4C4C FF0000 590000 190000
FFBD6C FF5400 591D00 271B00 FFFF4C FFFF00 595900 191900
88FF4C 54FF00 1D5900 142B00 4CFF4C 00FF00 005900 001900
4CFF5E 00FF19 00590D 001902 4CFF88 00FF55 00591D 001F12
4CFFB7 00FF99 005935 001912 4CC3FF 00A9FF 004152 001019
4C88FF 0055FF 001D59 000819 4C4CFF 0000FF 000059 000019
874CFF 5400FF 190064 0F0030 FF4CFF FF00FF 590059 190019
FF4C87 FF0054 59001D 220013 FF1500 993500 795100 436400
033900 005735 00547F 0000FF 00454F 2500CC 7F7F7F 202020
FF0000 BDFF2D AFED06 64FF09 108B00 00FF87 00A9FF 002AFF
3F00FF 7A00FF B21A7D 402100 FF4A00 88E106 72FF15 00FF00
3BFF26 59FF71 38FFCC 5B8AFF 3151C6 877FE9 D31DFF FF005D
FF7F00 B9B000 90FF00 835D07 392B00 144C10 0D5038 15152A
16205A 693C1C A8000A DE513D D86A1C FFE126 9EE12F 67B50F
1E1E30 DCFF6B 80FFBD 9A99FF 8E66FF 404040 757575 E0FFFF
A00000 350000 1AD000 074200 B9B000 3F3100 B35F00 4B1502
"""
VELOCITY_HEX = ["#" + h for h in _TABLE.split()]
assert len(VELOCITY_HEX) == 128

# The quick palette from v1 (display colour -> velocity). These are the colours
# the v1 files store, so they must stay exactly like this for compatibility.
BASIC_COLORS = [
    ("#000000", 0), ("#FFFFFF", 3), ("#FF0000", 5), ("#FF7F00", 9), ("#FFFF00", 13), ("#88FF4C", 16),
    ("#00FF00", 21), ("#00FFFF", 24), ("#4C4CFF", 44), ("#0000FF", 45), ("#8B00FF", 52), ("#FF00FF", 53),
]
# Show the v1 colours exactly as before for their velocities.
for _hex, _vel in BASIC_COLORS:
    VELOCITY_HEX[_vel] = _hex

HEX_TO_VELOCITY = {h.upper(): v for h, v in BASIC_COLORS}

# MIDI channel -> (group, short label). Channel 0-6 brightness, 7-10 pulsing, 11-15 blinking.
MODES = [
    ("brightness", "10%"), ("brightness", "25%"), ("brightness", "50%"), ("brightness", "65%"),
    ("brightness", "75%"), ("brightness", "90%"), ("brightness", "100%"),
    ("pulse", "1/16"), ("pulse", "1/8"), ("pulse", "1/4"), ("pulse", "1/2"),
    ("blink", "1/24"), ("blink", "1/16"), ("blink", "1/8"), ("blink", "1/4"), ("blink", "1/2"),
]
DEFAULT_MODE = 6  # 100 % brightness
BRIGHTNESS_LEVEL = [0.10, 0.25, 0.50, 0.65, 0.75, 0.90, 1.0]


def mode_badge(mode):
    """Short text shown on a pad, e.g. '50%', 'P1/4', 'B1/8' (empty for 100 %)."""
    group, short = MODES[mode]
    if group == "brightness":
        return "" if mode == DEFAULT_MODE else short
    return ("P" if group == "pulse" else "B") + short


def palette_order():
    """All 128 colours in a pleasant order: hue groups (4 shades each) first."""
    order = [4 * g + k for k in range(4) for g in range(16)]
    return order + list(range(64, 128))


def hex_to_rgb(h):
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def rgb_to_hex(r, g, b):
    return "#%02X%02X%02X" % (max(0, min(255, int(r))), max(0, min(255, int(g))), max(0, min(255, int(b))))


def mix(a, b, t):
    """Blend colour a towards colour b by t (0..1)."""
    ra, ga, ba = hex_to_rgb(a)
    rb, gb, bb = hex_to_rgb(b)
    return rgb_to_hex(ra + (rb - ra) * t, ga + (gb - ga) * t, ba + (bb - ba) * t)


def is_light(h):
    r, g, b = hex_to_rgb(h)
    return (0.299 * r + 0.587 * g + 0.114 * b) > 150
