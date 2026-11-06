"""Small drawing helpers and canvas widgets."""

import math
import tkinter as tk

from .palette import BRIGHTNESS_LEVEL, MODES, VELOCITY_HEX, mix

# Theme
BG = "#111216"
PANEL = "#17181D"
CARD = "#1F2127"
CARD_HOVER = "#272A31"
BORDER = "#2C2F37"
TEXT = "#ECEDEF"
MUTED = "#8B8F99"
ACCENT = "#4F8CFF"
ACCENT_HOVER = "#3B74E0"
DANGER = "#E5484D"
OK = "#3DD68C"
WARN = "#F5A524"
PAD_OFF = "#2A2C33"
RING_SELECTED = "#FFFFFF"
RING_HOVER = "#5C606B"


def round_rect(canvas, x1, y1, x2, y2, r, **kw):
    r = max(0, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
           x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return canvas.create_polygon(pts, smooth=True, **kw)


def move_round_rect(canvas, item, x1, y1, x2, y2, r):
    r = max(0, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    canvas.coords(item, x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
                  x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1)


def pad_fill(velocity, mode, off=PAD_OFF):
    """On-screen colour of a pad. Pulsing/blinking pads are shown steady (the badge tells the mode)."""
    if velocity == 0:
        return off
    level = BRIGHTNESS_LEVEL[mode] if MODES[mode][0] == "brightness" else 1.0
    return mix(off, VELOCITY_HEX[velocity], 0.18 + 0.82 * level)


class Thumb(tk.Canvas):
    """Tiny 8x8 preview of a layout."""

    def __init__(self, master, size, bg=CARD, **kw):
        super().__init__(master, width=size, height=size, bg=bg, highlightthickness=0, bd=0, **kw)
        self.size = size
        self._bg = bg

    def draw(self, pads):
        self.delete("all")
        gap = max(1, self.size // 40)
        cell = (self.size - gap * 9) / 8
        for note, (vel, mode) in enumerate(pads):
            row = 7 - note // 8
            col = note % 8
            x = gap + col * (cell + gap)
            y = gap + row * (cell + gap)
            self.create_rectangle(x, y, x + cell, y + cell, width=0,
                                  fill=pad_fill(vel, mode, off="#30333B"))


class SwatchGrid(tk.Canvas):
    """Grid of clickable colour swatches that resizes with its width."""

    def __init__(self, master, velocities, columns, on_pick, gap_ratio=0.18, radius_ratio=0.28,
                 bg=PANEL, max_cell=None, on_hover=None):
        super().__init__(master, height=10, bg=bg, highlightthickness=0, bd=0, cursor="hand2")
        self.velocities = list(velocities)
        self.columns = columns
        self.on_pick = on_pick
        self.on_hover = on_hover
        self.gap_ratio = gap_ratio
        self.radius_ratio = radius_ratio
        self.max_cell = max_cell
        self.selected = None
        self._items = {}
        self._rings = {}
        self._cells = []
        self._width = 0
        self.bind("<Configure>", self._on_configure)
        self.bind("<Button-1>", self._on_click)
        self.bind("<Motion>", self._on_motion)
        self.bind("<Leave>", lambda e: self.on_hover and self.on_hover(None))

    def _on_configure(self, event):
        if event.width != self._width:
            self._width = event.width
            self.redraw()

    def redraw(self):
        self.delete("all")
        self._items.clear()
        self._rings.clear()
        self._cells = []
        w = max(self._width, 10)
        rows = math.ceil(len(self.velocities) / self.columns)
        cell = w / (self.columns + (self.columns - 1) * self.gap_ratio)
        if self.max_cell:
            cell = min(cell, self.max_cell)
        gap = cell * self.gap_ratio
        height = rows * cell + (rows - 1) * gap
        self.configure(height=int(height + 4))
        pad = 2
        for i, vel in enumerate(self.velocities):
            r, c = divmod(i, self.columns)
            x1 = c * (cell + gap) + pad
            y1 = r * (cell + gap) + pad
            x2, y2 = x1 + cell - pad * 2 + 2, y1 + cell - pad * 2 + 2
            ring = round_rect(self, x1 - 2, y1 - 2, x2 + 2, y2 + 2, cell * self.radius_ratio + 2,
                              fill=self["bg"], outline="")
            fill = VELOCITY_HEX[vel] if vel else PAD_OFF
            item = round_rect(self, x1 + 1, y1 + 1, x2 - 1, y2 - 1, cell * self.radius_ratio,
                              fill=fill, outline="#000000" if vel == 0 else "")
            if vel == 0:
                # "off" marker: diagonal line
                self.create_line(x1 + cell * 0.3, y2 - cell * 0.3, x2 - cell * 0.3, y1 + cell * 0.3,
                                 fill=MUTED, width=max(1, cell / 16))
            self._items[vel] = item
            self._rings[vel] = ring
            self._cells.append((x1 - gap / 2, y1 - gap / 2, x2 + gap / 2, y2 + gap / 2, vel))
        self.set_selected(self.selected)

    def _hit(self, x, y):
        for x1, y1, x2, y2, vel in self._cells:
            if x1 <= x <= x2 and y1 <= y <= y2:
                return vel
        return None

    def _on_click(self, event):
        vel = self._hit(event.x, event.y)
        if vel is not None:
            self.on_pick(vel)

    def _on_motion(self, event):
        if self.on_hover:
            self.on_hover(self._hit(event.x, event.y))

    def set_selected(self, vel):
        if self.selected in self._rings:
            self.itemconfigure(self._rings[self.selected], fill=self["bg"])
        self.selected = vel
        if vel in self._rings:
            self.itemconfigure(self._rings[vel], fill=RING_SELECTED)
