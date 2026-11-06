"""The 8x8 pad matrix, drawn like the hardware."""

import sys
import tkinter as tk

from .palette import DEFAULT_MODE, is_light, mode_badge
from .widgets import (BG, CARD, CARD_HOVER, MUTED, PAD_OFF, RING_HOVER, RING_SELECTED, TEXT,
                      move_round_rect, pad_fill, round_rect)

IS_MAC = sys.platform == "darwin"
SELECTOR_RATIO = 0.55  # size of the row/column selector strip relative to a pad
DRAG_THRESHOLD = 5     # pixels the mouse must move before a click becomes a selection box
MARQUEE = "#7FA8FF"
RESIZE_DELAY_MS = 30   # redraw once the window size has settled a little

# Modifier bits in Tk event.state
SHIFT = 0x0001
CONTROL = 0x0004
COMMAND = 0x0008  # macOS


class MatrixView(tk.Canvas):
    def __init__(self, master, callbacks, all_label="All", bg=BG):
        super().__init__(master, bg=bg, highlightthickness=0, bd=0)
        self.cb = callbacks
        self.pads = [(0, DEFAULT_MODE)] * 64
        self.selected = set()
        self.hover = None
        self._geom = None
        self._size = None
        self._resize_job = None
        self._pad_items = {}
        self._ring_items = {}
        self._badge_items = {}
        self._sel_items = {}  # ("row", r) / ("col", c) / ("all",) -> (rect, label)
        self._shown = {}      # note -> (fill, badge, badge colour, ring) currently drawn
        self._dragging = False
        self._drag_start = None
        self._drag_moved = False
        self._create_items(all_label)
        self.bind("<Configure>", self._on_configure)
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<Shift-ButtonPress-1>", lambda e: self._press(e, additive=True))
        self.bind("<B1-Motion>", self._drag)
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<Motion>", self._motion)
        self.bind("<Leave>", self._leave)
        # Right-click = pick colour. On macOS also Ctrl-click; on Windows/Linux Ctrl-click adds.
        for seq in ("<Button-2>", "<Button-3>") + (("<Control-Button-1>",) if IS_MAC else ()):
            self.bind(seq, self._pick)
        add_seq = "<Command-ButtonPress-1>" if IS_MAC else "<Control-ButtonPress-1>"
        self.bind(add_seq, lambda e: self._press(e, additive=True))

    # -- geometry ----------------------------------------------------------
    def _create_items(self, all_label):
        for note in range(64):
            self._pad_items[note] = round_rect(self, 0, 0, 1, 1, 1, fill=PAD_OFF, outline="")
            self._ring_items[note] = round_rect(self, 0, 0, 1, 1, 1, fill="", outline="", width=2)
            self._badge_items[note] = self.create_text(0, 0, text="", fill=TEXT, anchor="se")
        for r in range(8):
            self._sel_items[("row", r)] = self._make_selector(None)
        for c in range(8):
            self._sel_items[("col", c)] = self._make_selector(None)
        self._sel_items[("all",)] = self._make_selector(all_label)
        # selection box ("window") drawn while dragging
        self._marquee = self.create_rectangle(0, 0, 0, 0, outline=MARQUEE, width=2, dash=(6, 4),
                                              state="hidden")

    def set_all_label(self, text):
        self.itemconfigure(self._sel_items[("all",)][1], text=text)

    def _make_selector(self, text):
        rect = round_rect(self, 0, 0, 1, 1, 1, fill=CARD, outline="")
        if text:
            label = self.create_text(0, 0, text=text, fill=MUTED)
        else:  # small arrow pointing at the row / column
            label = self.create_polygon(0, 0, 0, 0, 0, 0, fill=MUTED, outline="")
        return rect, label

    def _on_configure(self, event):
        size = (event.width, event.height)
        if size == self._size:
            return
        self._size = size
        if self._resize_job is not None:
            self.after_cancel(self._resize_job)
        delay = RESIZE_DELAY_MS if self._geom else 0
        self._resize_job = self.after(delay, self._layout)

    def _layout(self):
        self._resize_job = None
        w, h = self.winfo_width(), self.winfo_height()
        if w < 20 or h < 20:
            return
        units = 8 + SELECTOR_RATIO + 0.25
        cell = min(w / units, h / units)
        gap = cell * 0.12
        total = cell * units
        self._geom = (( w - total) / 2, (h - total) / 2, cell, gap)
        radius = cell * 0.16
        ring_w = max(2, round(cell * 0.04))
        ring_in = ring_w / 2  # the selection outline sits inside the pad, never touching neighbours
        font = ("Helvetica", -max(8, int(cell * 0.17)), "bold")
        for note in range(64):
            x1, y1, x2, y2 = self._pad_box(note)
            move_round_rect(self, self._pad_items[note], x1, y1, x2, y2, radius)
            move_round_rect(self, self._ring_items[note], x1 + ring_in, y1 + ring_in,
                            x2 - ring_in, y2 - ring_in, max(1, radius - ring_in))
            self.itemconfigure(self._ring_items[note], width=ring_w)
            self.coords(self._badge_items[note], x2 - cell * 0.08, y2 - cell * 0.06)
            self.itemconfigure(self._badge_items[note], font=font)
        sel_font = ("Helvetica", -max(8, int(cell * 0.2)))
        for key, (rect, label) in self._sel_items.items():
            x1, y1, x2, y2 = self._selector_box(key)
            move_round_rect(self, rect, x1, y1, x2, y2, min(x2 - x1, y2 - y1) * 0.3)
            cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
            a = cell * 0.065
            if key[0] == "row":  # arrow pointing left
                self.coords(label, cx - a, cy, cx + a, cy - a * 1.1, cx + a, cy + a * 1.1)
            elif key[0] == "col":  # arrow pointing up
                self.coords(label, cx, cy - a, cx - a * 1.1, cy + a, cx + a * 1.1, cy + a)
            else:
                self.coords(label, cx, cy)
                self.itemconfigure(label, font=sel_font)
        self.refresh()

    def _pad_box(self, note):
        ox, oy, cell, gap = self._geom
        row = 7 - note // 8
        col = note % 8
        x1 = ox + col * cell + gap / 2
        y1 = oy + row * cell + gap / 2
        return x1, y1, x1 + cell - gap, y1 + cell - gap

    def _selector_box(self, key):
        ox, oy, cell, gap = self._geom
        strip = cell * SELECTOR_RATIO
        sx = ox + 8 * cell + cell * 0.25  # right strip (rows)
        sy = oy + 8 * cell + cell * 0.25  # bottom strip (columns)
        if key[0] == "row":
            y1 = oy + key[1] * cell + gap / 2
            return sx, y1 + cell * 0.15, sx + strip, y1 + cell - gap - cell * 0.15
        if key[0] == "col":
            x1 = ox + key[1] * cell + gap / 2
            return x1 + cell * 0.1, sy, x1 + cell - gap - cell * 0.1, sy + strip
        return sx, sy, sx + strip, sy + strip

    def _hit(self, x, y):
        if not self._geom:
            return None
        ox, oy, cell, gap = self._geom
        col = int((x - ox) // cell)
        row = int((y - oy) // cell)
        if 0 <= col < 8 and 0 <= row < 8 and x >= ox and y >= oy:
            return ("pad", (7 - row) * 8 + col)
        for key in self._sel_items:
            x1, y1, x2, y2 = self._selector_box(key)
            if x1 - 2 <= x <= x2 + 2 and y1 - 2 <= y <= y2 + 2:
                if key[0] == "row":
                    return ("row", 7 - key[1])  # hardware row index (0 = bottom)
                return key if key[0] == "all" else ("col", key[1])
        return None

    def _notes_in_rect(self, x1, y1, x2, y2):
        x1, x2 = sorted((x1, x2))
        y1, y2 = sorted((y1, y2))
        notes = set()
        for note in range(64):
            px1, py1, px2, py2 = self._pad_box(note)
            if px1 <= x2 and px2 >= x1 and py1 <= y2 and py2 >= y1:
                notes.add(note)
        return notes

    # -- events ------------------------------------------------------------
    def _press(self, event, additive=False):
        hit = self._hit(event.x, event.y)
        if not hit or hit[0] == "pad":
            # Click on a pad, or start of a selection box (also from empty space)
            if not self._geom:
                return "break"
            self._dragging = True
            self._drag_start = (event.x, event.y)
            self._drag_moved = False
            self.cb["press"](hit[1] if hit else None, additive)
        elif hit[0] == "row":
            self.cb["row"](hit[1], additive)
        elif hit[0] == "col":
            self.cb["col"](hit[1], additive)
        else:
            self.cb["all"](additive)
        return "break"

    def _drag(self, event):
        if not self._dragging:
            return
        sx, sy = self._drag_start
        if not self._drag_moved and abs(event.x - sx) < DRAG_THRESHOLD and abs(event.y - sy) < DRAG_THRESHOLD:
            return
        self._drag_moved = True
        self.coords(self._marquee, sx, sy, event.x, event.y)
        self.itemconfigure(self._marquee, state="normal")
        self.tag_raise(self._marquee)
        self.cb["rect"](self._notes_in_rect(sx, sy, event.x, event.y))

    def _release(self, event):
        if self._dragging:
            self._dragging = False
            self.itemconfigure(self._marquee, state="hidden")
            self.cb["release"](self._drag_moved)

    def _pick(self, event):
        hit = self._hit(event.x, event.y)
        if hit and hit[0] == "pad":
            self.cb["pick"](hit[1])
        return "break"

    def _motion(self, event):
        self._set_hover(self._hit(event.x, event.y))

    def _leave(self, event):
        self._set_hover(None)

    def _set_hover(self, hit):
        if hit == self.hover:
            return
        old, self.hover = self.hover, hit
        for h in (old, hit):
            if h is None:
                continue
            if h[0] == "pad":
                self._update_pad(h[1])
            else:
                key = ("row", 7 - h[1]) if h[0] == "row" else h
                rect, label = self._sel_items[key]
                on = h == self.hover
                self.itemconfigure(rect, fill=CARD_HOVER if on else CARD)
                self.itemconfigure(label, fill=TEXT if on else MUTED)
        self.configure(cursor="hand2" if hit else "")
        self.cb["hover"](hit[1] if hit and hit[0] == "pad" else None)

    # -- drawing -----------------------------------------------------------
    def set_state(self, pads, selected):
        self.pads = list(pads)
        self.selected = set(selected)
        self.refresh(only_changes=True)

    def refresh(self, only_changes=False):
        if not self._geom:
            return
        if not only_changes:
            self._shown.clear()
        for note in range(64):
            self._update_pad(note)

    def _update_pad(self, note):
        """Redraw one pad - only the canvas items whose look actually changed."""
        vel, mode = self.pads[note]
        fill = pad_fill(vel, mode)
        badge = mode_badge(mode) if vel else ""
        badge_colour = "#111111" if vel and is_light(fill) else "#FFFFFF"
        if note in self.selected:
            ring = RING_SELECTED
        elif self.hover == ("pad", note):
            ring = RING_HOVER
        else:
            ring = ""
        new = (fill, badge, badge_colour, ring)
        old = self._shown.get(note)
        if old == new:
            return
        self._shown[note] = new
        if old is None or old[0] != fill:
            self.itemconfigure(self._pad_items[note], fill=fill)
        if old is None or old[1:3] != new[1:3]:
            self.itemconfigure(self._badge_items[note], text=badge, fill=badge_colour)
        if old is None or old[3] != ring:
            self.itemconfigure(self._ring_items[note], outline=ring)
