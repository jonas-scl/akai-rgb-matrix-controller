"""Main window."""

import os
import subprocess
import sys
import tkinter as tk
import tkinter.font as tkfont
import traceback
from datetime import datetime
from tkinter import filedialog, messagebox

import customtkinter as ctk

from . import APP_NAME, AUTHOR, VERSION
from .i18n import LANGUAGES, S, colour_name, language, set_language, system_language, t
from .layout import EXTENSION, empty_layout, load_file, save_file
from .matrix import MatrixView
from .midi import MidiLink, normalize, pick_apc
from .palette import BASIC_COLORS, DEFAULT_MODE, MODES, VELOCITY_HEX, palette_order
from .storage import Storage
from .widgets import (ACCENT, ACCENT_HOVER, BG, BORDER, CARD, CARD_HOVER, DANGER, MUTED, OK,
                      PANEL, TEXT, WARN, SwatchGrid, Thumb, round_rect)

IS_MAC = sys.platform == "darwin"
MOD = "Command" if IS_MAC else "Control"
POLL_MS = 2000
AUTOSAVE_MS = 250
UNDO_LIMIT = 200
MODE_GROUPS = ["brightness", "pulse", "blink"]
PRESET_NAMES = set(S["preset_default"]) | set(S["preset_test"])


def mod_label():
    return "⌘" if IS_MAC else t("mod_ctrl")


def mode_long(mode):
    group, short = MODES[mode]
    return t("mode_" + group, v=short.replace("%", " %"))


def rel_time(iso):
    try:
        then = datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return ""
    delta = (datetime.now() - then).total_seconds()
    if delta < 60:
        return t("just_now")
    if delta < 3600:
        return t("min_ago", n=int(delta // 60))
    if then.date() == datetime.now().date():
        return t("today_at", time=then.strftime("%H:%M"))
    return then.strftime(t("date_fmt"))


class App(ctk.CTk):
    def __init__(self, storage=None, midi=None, open_path=None):
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        super().__init__(fg_color=BG)
        self.title("%s %s" % (APP_NAME, VERSION))
        self._set_icon()
        self.storage = storage or Storage()
        set_language(self.storage.get("language") or system_language())
        self.link = midi or MidiLink()
        self.link.set_scheduler(self.after, self.after_cancel)
        self.link.release_port = bool(self.storage.get("release_port", True))

        # --- state ---
        self.pads = list(empty_layout())
        self.selected = set()
        self.color = int(self.storage.get("color", 3))
        self.mode = int(self.storage.get("mode", DEFAULT_MODE))
        self.layout_name = ""
        self.layout_base = None
        self.undo_stack = []
        self.redo_stack = []
        self.sent = [None] * 64          # what the device shows (as far as we know)
        self._pending_notes = set()
        self._flush_job = None
        self._autosave_job = None
        self._drag_action = None
        self._drag_base = None
        self._device_present = False
        self._port_names = []
        self._drag_additive = False
        self._hint_flash = None
        self._list_rows = []
        self._list_signature = None
        self._tk_fonts = {}
        self._cfg_cache = {}
        self._shown_mode = None

        self._build_ui()
        self._bind_keys()
        self._restore_geometry()

        # Restore the last state (autosave) or the standard layout.
        current = self.storage.load_current()
        if current:
            self.pads = list(current[0])
            self.layout_name = current[1] if current[1] != "current" else ""
            base = self.storage.get("base_name")
            self.layout_name = base if base is not None else self.layout_name
            self.layout_base = tuple(self.pads) if self.storage.get("base_clean", True) else None
        else:
            self.pads = list(self.storage.load_standard())
            self.layout_name = t("preset_default")
            self.layout_base = tuple(self.pads)

        # Device: last used one ("" = deliberately none), otherwise the first APC mini mk2 found.
        target = self.storage.get("device")
        if target is None:
            target = pick_apc(self.link.port_names())
        self.link.set_target(target or None)

        self._refresh_all()
        self._refresh_lists()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(50, self._poll_devices)  # sends the current state as soon as the device is there
        if open_path:
            self.after(200, lambda: self.load_path(open_path))

    # ------------------------------------------------------------------ UI
    def _font(self, size=13, weight="normal"):
        return ctk.CTkFont(size=size, weight=weight)

    def _build_ui(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # ---------- header ----------
        header = ctk.CTkFrame(self, fg_color=PANEL, corner_radius=0, height=56)
        header.grid(row=0, column=0, columnspan=3, sticky="ew")
        header.grid_columnconfigure(2, weight=1)
        ctk.CTkLabel(header, text="APC RGB", font=self._font(17, "bold"), text_color=TEXT).grid(
            row=0, column=0, padx=(18, 4), pady=12)
        ctk.CTkLabel(header, text="Controller", font=self._font(17), text_color=MUTED).grid(
            row=0, column=1, padx=(0, 18), pady=12, sticky="w")

        dev = ctk.CTkFrame(header, fg_color="transparent")
        dev.grid(row=0, column=2, sticky="w")
        self.status_dot = tk.Canvas(dev, width=12, height=12, bg=PANEL, highlightthickness=0, bd=0)
        self._dot = self.status_dot.create_oval(1, 1, 11, 11, fill=MUTED, outline="")
        self.status_dot.pack(side="left", padx=(0, 8))
        self.device_menu = ctk.CTkOptionMenu(
            dev, values=[t("no_device")], command=self._on_device_chosen, width=230, height=32,
            fg_color=CARD, button_color=CARD, button_hover_color=CARD_HOVER,
            dropdown_fg_color=CARD, dropdown_hover_color=CARD_HOVER, text_color=TEXT,
            font=self._font(13), dropdown_font=self._font(13), dynamic_resizing=False)
        self.device_menu.pack(side="left")
        self.status_label = ctk.CTkLabel(dev, text="", font=self._font(12), text_color=MUTED)
        self.status_label.pack(side="left", padx=12)

        self.btn_resend = ctk.CTkButton(header, text=t("resend"), width=110, height=32,
                                        fg_color=CARD, hover_color=CARD_HOVER, text_color=TEXT,
                                        font=self._font(13), command=self.resend_all)
        self.btn_resend.grid(row=0, column=3, padx=6)
        self.btn_menu = ctk.CTkButton(header, text="•••", width=44, height=32, fg_color=CARD,
                                      hover_color=CARD_HOVER, text_color=TEXT, font=self._font(13, "bold"),
                                      command=self._show_main_menu)
        self.btn_menu.grid(row=0, column=4, padx=(0, 14))

        # ---------- left: layouts ----------
        left = ctk.CTkFrame(self, fg_color=PANEL, corner_radius=0, width=260)
        left.grid(row=1, column=0, sticky="ns")
        left.grid_propagate(False)
        left.grid_rowconfigure(0, weight=1)
        left.grid_columnconfigure(0, weight=1)
        self.list_frame = ctk.CTkScrollableFrame(left, fg_color=PANEL, corner_radius=0,
                                                 scrollbar_button_color=CARD,
                                                 scrollbar_button_hover_color=CARD_HOVER)
        self.list_frame.grid(row=0, column=0, sticky="nsew", padx=(4, 0), pady=(8, 0))
        self.list_frame.grid_columnconfigure(0, weight=1)
        bottom = ctk.CTkFrame(left, fg_color="transparent")
        bottom.grid(row=1, column=0, sticky="ew", padx=12, pady=12)
        bottom.grid_columnconfigure((0, 1), weight=1)
        ctk.CTkButton(bottom, text=t("save"), height=34, fg_color=ACCENT, hover_color=ACCENT_HOVER,
                      font=self._font(13, "bold"), command=self.save_to_library).grid(
            row=0, column=0, sticky="ew", padx=(0, 4))
        ctk.CTkButton(bottom, text=t("as_default"), height=34, fg_color=CARD, hover_color=CARD_HOVER,
                      text_color=TEXT, font=self._font(13), command=self.save_as_standard).grid(
            row=0, column=1, sticky="ew", padx=(4, 0))

        # ---------- centre: matrix ----------
        centre = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        centre.grid(row=1, column=1, sticky="nsew")
        centre.grid_rowconfigure(1, weight=1)
        centre.grid_columnconfigure(0, weight=1)
        title_row = ctk.CTkFrame(centre, fg_color="transparent")
        title_row.grid(row=0, column=0, sticky="ew", padx=24, pady=(18, 0))
        self.title_label = ctk.CTkLabel(title_row, text="", font=self._font(20, "bold"), text_color=TEXT)
        self.title_label.pack(side="left")
        self.modified_label = ctk.CTkLabel(title_row, text="", font=self._font(13), text_color=MUTED)
        self.modified_label.pack(side="left", padx=10)
        self.selection_label = ctk.CTkLabel(title_row, text="", font=self._font(13), text_color=MUTED)
        self.selection_label.pack(side="right")

        self.matrix = MatrixView(centre, {
            "press": self._pad_press, "rect": self._pad_rect, "release": self._pad_release,
            "pick": self._pad_pick, "row": self._select_row, "col": self._select_col,
            "all": self._select_all_toggle, "hover": self._pad_hover,
        })
        self.matrix.grid(row=1, column=0, sticky="nsew", padx=16, pady=8)

        tools = ctk.CTkFrame(centre, fg_color="transparent")
        tools.grid(row=2, column=0, pady=(0, 6))
        self._tools = []

        def tool(text, cmd, danger=False, width=0):
            b = ctk.CTkButton(tools, text=text, command=cmd, height=32, width=width or 28,
                              fg_color=CARD, hover_color=CARD_HOVER,
                              text_color=DANGER if danger else TEXT, font=self._font(13))
            self._tools.append(b)
            return b

        tool(t("select_all"), self.select_all)
        tool(t("clear_selection"), self.clear_selection)
        tool(t("turn_off_selected"), self.turn_off_selected)
        self.btn_undo = tool(t("undo"), self.undo)
        self.btn_redo = tool(t("redo"), self.redo)
        tool(t("all_off"), self.turn_off_all, danger=True)

        self.hint_label = ctk.CTkLabel(centre, text="", font=self._font(12), text_color=MUTED, height=20)
        self.hint_label.grid(row=3, column=0, pady=(0, 14), padx=12)
        self._tools_cols = None
        self._arrange_tools(6)
        centre.bind("<Configure>", self._on_centre_resize, add="+")

        # ---------- right: colour & mode ----------
        right = ctk.CTkScrollableFrame(self, fg_color=PANEL, corner_radius=0, width=300,
                                       scrollbar_button_color=CARD, scrollbar_button_hover_color=CARD_HOVER)
        right.grid(row=1, column=2, sticky="ns")
        right.grid_columnconfigure(0, weight=1)
        self.right = right

        current = ctk.CTkFrame(right, fg_color=CARD, corner_radius=12)
        current.grid(row=0, column=0, sticky="ew", padx=14, pady=(16, 6))
        current.grid_columnconfigure(1, weight=1)
        self.current_chip = tk.Canvas(current, width=40, height=40, bg=CARD, highlightthickness=0, bd=0)
        self._chip = round_rect(self.current_chip, 1, 1, 39, 39, 9, fill="#FFFFFF", outline="")
        self.current_chip.grid(row=0, column=0, rowspan=2, padx=12, pady=12)
        self.current_name = ctk.CTkLabel(current, text="", font=self._font(14, "bold"), text_color=TEXT, anchor="w")
        self.current_name.grid(row=0, column=1, sticky="sw", pady=(12, 0))
        self.current_mode = ctk.CTkLabel(current, text="", font=self._font(12), text_color=MUTED, anchor="w")
        self.current_mode.grid(row=1, column=1, sticky="nw", pady=(0, 12))

        self._section(right, t("colour"), 1)
        self.basic_grid = SwatchGrid(right, [v for _, v in BASIC_COLORS], 6, self.set_color,
                                     max_cell=46, on_hover=self._swatch_hover)
        self.basic_grid.grid(row=2, column=0, sticky="ew", padx=16)

        self.more_open = bool(self.storage.get("more_colors", False))
        self.more_btn = ctk.CTkButton(right, text="", height=28, fg_color="transparent", hover_color=CARD,
                                      text_color=MUTED, anchor="w", font=self._font(12),
                                      command=self._toggle_more_colors)
        self.more_btn.grid(row=3, column=0, sticky="ew", padx=10, pady=(6, 0))
        self.all_grid = SwatchGrid(right, palette_order(), 16, self.set_color, gap_ratio=0.14,
                                   radius_ratio=0.2, on_hover=self._swatch_hover)
        self._apply_more_colors()

        self._section(right, t("mode"), 5)
        self.mode_buttons = {}
        row = 6
        for group in MODE_GROUPS:
            ctk.CTkLabel(right, text=t("brightness_pct" if group == "brightness" else group),
                         font=self._font(12), text_color=MUTED, anchor="w").grid(
                row=row, column=0, sticky="w", padx=18, pady=(6, 2))
            row += 1
            channels = [ch for ch, m in enumerate(MODES) if m[0] == group]
            labels = [MODES[ch][1].rstrip("%") for ch in channels]
            seg = ctk.CTkSegmentedButton(
                right, values=labels, height=32, font=self._font(12),
                fg_color=CARD, unselected_color=CARD, unselected_hover_color=CARD_HOVER,
                selected_color=ACCENT, selected_hover_color=ACCENT_HOVER, text_color=TEXT,
                command=lambda value, chs=channels, labs=labels: self.set_mode(chs[labs.index(value)]))
            seg.grid(row=row, column=0, sticky="ew", padx=16)
            row += 1
            self.mode_buttons[group] = (seg, channels, labels)

        ctk.CTkLabel(right, text=t("help"), font=self._font(11), text_color=MUTED, justify="left",
                     anchor="w", wraplength=260).grid(row=row, column=0, sticky="w", padx=18, pady=(18, 16))

    def _arrange_tools(self, cols):
        """Toolbar in one row (wide window) or two rows (narrow window)."""
        if cols == self._tools_cols:
            return
        self._tools_cols = cols
        for i, b in enumerate(self._tools):
            b.grid(row=i // cols, column=i % cols, padx=3, pady=2)

    def _on_centre_resize(self, event):
        scale = ctk.ScalingTracker.get_widget_scaling(self)
        self._arrange_tools(6 if event.width / scale >= 560 else 3)
        self.hint_label.configure(wraplength=max(200, event.width / scale - 40))

    def _section(self, parent, text, row):
        ctk.CTkLabel(parent, text=text.upper(), font=self._font(11, "bold"), text_color=MUTED,
                     anchor="w").grid(row=row, column=0, sticky="w", padx=18, pady=(18, 6))

    def _toggle_more_colors(self):
        self.more_open = not self.more_open
        self.storage.set("more_colors", self.more_open)
        self._apply_more_colors()

    def _apply_more_colors(self):
        self.more_btn.configure(text=t("fewer_colours") if self.more_open else t("more_colours"))
        if self.more_open:
            self.all_grid.grid(row=4, column=0, sticky="ew", padx=16, pady=(4, 0))
            self.all_grid.set_selected(self.color)
        else:
            self.all_grid.grid_forget()

    # ------------------------------------------------------------ sidebar
    def _tk_font(self, size, weight="normal"):
        """Plain Tk font matching customtkinter's look (incl. its DPI scaling)."""
        key = (size, weight)
        if key not in self._tk_fonts:
            family = ctk.CTkFont().cget("family")
            scale = ctk.ScalingTracker.get_widget_scaling(self)
            self._tk_fonts[key] = tkfont.Font(family=family, size=-round(size * scale), weight=weight)
        return self._tk_fonts[key]

    def _refresh_lists(self):
        """Rebuild the sidebar - only if its content actually changed (plain Tk widgets = fast)."""
        standard = self.storage.load_standard()
        test = self.storage.load_colour_test()
        lib = self.storage.library()
        history = list(self.storage.history)
        signature = (standard, self.storage.has_custom_standard(),
                     tuple((it.name, it.mtime, it.pads) for it in lib),
                     tuple((h["name"], h["time"], h["pads"]) for h in history))
        if signature == self._list_signature:
            self._update_list_highlight()
            return
        self._list_signature = signature

        for child in self.list_frame.winfo_children():
            child.destroy()
        self._list_rows = []
        row = 0

        def header(text, action_text=None, action=None):
            nonlocal row
            f = tk.Frame(self.list_frame, bg=PANEL)
            f.grid(row=row, column=0, sticky="ew", padx=8, pady=(16 if row else 6, 4))
            tk.Label(f, text=text.upper(), bg=PANEL, fg=MUTED, font=self._tk_font(11, "bold")).pack(side="left")
            if action_text:
                link = tk.Label(f, text=action_text, bg=PANEL, fg=MUTED, font=self._tk_font(11), cursor="hand2")
                link.pack(side="right")
                link.bind("<Button-1>", lambda e: action())
                link.bind("<Enter>", lambda e: link.configure(fg=TEXT))
                link.bind("<Leave>", lambda e: link.configure(fg=MUTED))
            row += 1

        def item(pads, title, subtitle, on_click, on_menu=None):
            nonlocal row
            self._list_item(row, pads, title, subtitle, on_click, on_menu)
            row += 1

        header(t("templates"))
        item(standard, t("preset_default"),
             t("default_custom") if self.storage.has_custom_standard() else t("default_builtin"),
             lambda p=standard: self.load_layout(p, t("preset_default")), self._standard_menu)
        item(test, t("preset_test"), t("test_sub"),
             lambda p=test: self.load_layout(p, t("preset_test")))

        header(t("my_layouts"), t("new"), self.save_to_library)
        if not lib:
            self._empty_hint(row, t("nothing_saved"))
            row += 1
        for it in lib:
            item(it.pads, it.name, rel_time(datetime.fromtimestamp(it.mtime).isoformat()),
                 lambda it=it: self.load_layout(it.pads, it.name),
                 lambda e, it=it: self._library_menu(e, it))

        header(t("recent"), t("clear") if history else None, self._clear_history)
        if not history:
            self._empty_hint(row, t("empty"))
            row += 1
        for i, h in enumerate(history):
            item(h["pads"], h["name"] or t("untitled"), rel_time(h["time"]),
                 lambda h=h: self.load_layout(h["pads"], h["name"]),
                 lambda e, i=i, h=h: self._history_menu(e, i, h))
        self._update_list_highlight(force=True)

    def _empty_hint(self, row, text):
        tk.Label(self.list_frame, text=text, bg=PANEL, fg=MUTED, font=self._tk_font(12), anchor="w").grid(
            row=row, column=0, sticky="w", padx=10, pady=2)

    def _list_item(self, row, pads, title, subtitle, on_click, on_menu):
        frame = tk.Frame(self.list_frame, bg=PANEL, highlightthickness=1, highlightbackground=PANEL,
                         highlightcolor=PANEL, cursor="hand2")
        frame.grid(row=row, column=0, sticky="ew", padx=4, pady=1)
        frame.grid_columnconfigure(1, weight=1)
        thumb = Thumb(frame, round(40 * ctk.ScalingTracker.get_widget_scaling(self)), bg=CARD, cursor="hand2")
        thumb.draw(pads)
        thumb.grid(row=0, column=0, rowspan=2, padx=8, pady=6)
        name = tk.Label(frame, text=title, bg=PANEL, fg=TEXT, font=self._tk_font(13, "bold"), anchor="w",
                        cursor="hand2")
        name.grid(row=0, column=1, sticky="sw", padx=(0, 8), pady=(6, 0))
        sub = tk.Label(frame, text=subtitle, bg=PANEL, fg=MUTED, font=self._tk_font(11), anchor="w",
                       cursor="hand2")
        sub.grid(row=1, column=1, sticky="nw", padx=(0, 8), pady=(0, 6))

        def paint(colour):
            for w in (frame, name, sub):
                w.configure(bg=colour)

        for w in (frame, thumb, name, sub):
            w.bind("<Button-1>", lambda e: on_click())
            w.bind("<Enter>", lambda e: paint(CARD))
            w.bind("<Leave>", lambda e: paint(PANEL))
            if on_menu:
                for seq in ("<Button-2>", "<Button-3>", "<Control-Button-1>"):
                    w.bind(seq, lambda e: (on_menu(e), "break")[1])
        self._list_rows.append([frame, tuple(pads), None])

    def _update_list_highlight(self, force=False):
        """Blue frame around the sidebar entries that match the current pads."""
        current = tuple(self.pads)
        for entry in self._list_rows:
            frame, pads, state = entry
            active = pads == current
            if active != state or force:
                entry[2] = active
                colour = ACCENT if active else PANEL
                try:
                    frame.configure(highlightbackground=colour, highlightcolor=colour)
                except tk.TclError:
                    pass

    def _popup(self, event, entries):
        menu = tk.Menu(self, tearoff=0)
        for entry in entries:
            if entry is None:
                menu.add_separator()
            else:
                menu.add_command(label=entry[0], command=entry[1])
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _standard_menu(self, event):
        self._popup(event, [
            (t("m_load"), lambda: self.load_layout(self.storage.load_standard(), t("preset_default"))),
            (t("m_save_default"), self.save_as_standard),
            None,
            (t("m_reset_default"), self.reset_standard),
        ])

    def _library_menu(self, event, it):
        self._popup(event, [
            (t("m_load"), lambda: self.load_layout(it.pads, it.name)),
            (t("m_overwrite"), lambda: self._overwrite_library(it)),
            (t("m_rename"), lambda: self._rename_library(it)),
            (t("m_export"), lambda: self.export_file(it.pads, it.name)),
            None,
            (t("m_delete"), lambda: self._delete_library(it)),
        ])

    def _history_menu(self, event, index, h):
        self._popup(event, [
            (t("m_load"), lambda: self.load_layout(h["pads"], h["name"])),
            (t("m_save_to_lib"), lambda: self.save_to_library(h["pads"], h["name"])),
            None,
            (t("m_remove_history"), lambda: (self.storage.remove_history(index), self._refresh_lists())),
        ])

    def _show_main_menu(self):
        ml = mod_label()
        m = tk.Menu(self, tearoff=0)
        m.add_command(label=t("m_open"), accelerator=ml + "O", command=self.open_file)
        m.add_command(label=t("m_export"), accelerator=ml + "E", command=self.export_file)
        m.add_command(label=t("m_save_to_lib"), accelerator=ml + "S", command=self.save_to_library)
        m.add_separator()
        m.add_command(label=t("m_save_default"), command=self.save_as_standard)
        m.add_command(label=t("m_reset_default"), command=self.reset_standard)
        m.add_separator()
        m.add_command(label=t("undo"), accelerator=ml + "Z", command=self.undo)
        m.add_command(label=t("redo"), accelerator=ml + ("⇧Z" if IS_MAC else "Y"), command=self.redo)
        m.add_separator()
        m.add_command(label=t("m_resend"), accelerator=ml + "R", command=self.resend_all)
        self._release_var = tk.BooleanVar(value=self.link.release_port)
        m.add_checkbutton(label=t("m_release"), variable=self._release_var, command=self._toggle_release)
        lang = tk.Menu(m, tearoff=0)
        self._lang_var = tk.StringVar(value=language())
        for code, name in LANGUAGES:
            lang.add_radiobutton(label=name, value=code, variable=self._lang_var,
                                 command=lambda c=code: self.set_ui_language(c))
        m.add_cascade(label=t("m_language") + " / Language", menu=lang)
        m.add_separator()
        m.add_command(label=t("m_data_dir"), command=self.open_data_dir)
        m.add_command(label=t("m_licenses"), command=self.show_licenses)
        m.add_command(label=t("m_about"), command=self.show_about)
        x = self.btn_menu.winfo_rootx()
        y = self.btn_menu.winfo_rooty() + self.btn_menu.winfo_height() + 4
        try:
            m.tk_popup(x, y)
        finally:
            m.grab_release()

    def set_ui_language(self, code):
        """Switch the language and rebuild the window (state is kept)."""
        if code == language():
            return
        set_language(code)
        self.storage.set("language", code)
        if self._hint_flash is not None:
            self.after_cancel(self._hint_flash)
            self._hint_flash = None
        for child in self.winfo_children():
            child.destroy()
        self._cfg_cache.clear()
        self._shown_mode = None
        self._list_signature = None
        self._list_rows = []
        self._build_ui()
        self._refresh_all()
        self._refresh_lists()
        self._port_names = None
        self._update_device_values(self.link.port_names())
        self._update_status()

    # ------------------------------------------------------------ keys
    def _bind_keys(self):
        def bind(key, func, shift=False):
            seq = "<%s-%s%s>" % (MOD, "Shift-" if shift else "", key)
            self.bind(seq, lambda e: (func(), "break")[1])

        bind("z", self.undo)
        bind("Z", self.redo, shift=True)
        bind("y", self.redo)
        bind("a", self.select_all)
        bind("s", self.save_to_library)
        bind("o", self.open_file)
        bind("e", self.export_file)
        bind("r", self.resend_all)
        self.bind("<Escape>", lambda e: self.clear_selection())
        self.bind("<Delete>", lambda e: self.turn_off_selected())
        self.bind("<BackSpace>", lambda e: self.turn_off_selected())

    # ------------------------------------------------------------ geometry
    def _restore_geometry(self):
        self.minsize(900, 600)
        geo = self.storage.get("geometry")
        if isinstance(geo, str) and "x" in geo:
            try:
                self.geometry(geo)
                return
            except tk.TclError:
                pass
        self.geometry("1240x780")

    # ------------------------------------------------------------ editing
    def _snapshot(self):
        snap = tuple(self.pads)
        if not self.undo_stack or self.undo_stack[-1] != snap:
            self.undo_stack.append(snap)
            del self.undo_stack[:-UNDO_LIMIT]
        self.redo_stack.clear()

    def _set_pad(self, note, vel, mode):
        if self.pads[note] != (vel, mode):
            self.pads[note] = (vel, mode)
            self._pending_notes.add(note)

    def _changed(self):
        """Something changed: redraw, send to the device and autosave."""
        self.matrix.set_state(self.pads, self.selected)
        self._refresh_info()
        self._schedule_flush()
        self._schedule_autosave()

    def _pad_press(self, note, additive=False):
        """Mouse down on a pad (note) or on empty space (None).

        A new click / box starts a new marking; with Shift (or Ctrl/Cmd) it is added to the
        current one. Starting on a marked pad unmarks instead. A click into empty space unmarks all.
        """
        if note is not None and note in self.selected:
            self._drag_action = "unselect"
            base_sel = set(self.selected)
        else:
            self._drag_action = "select"
            base_sel = set(self.selected) if additive else set()
            self._snapshot()
        self._drag_base = (tuple(self.pads), base_sel)
        self._pad_rect({note} if note is not None else set())

    def _pad_rect(self, notes):
        """Pads inside the click / selection box. Pads that leave the box get their old state back."""
        if self._drag_action is None:
            return
        base_pads, base_sel = self._drag_base
        selected = set(base_sel)
        for n in range(64):
            if n in notes and self._drag_action == "select":
                self._set_pad(n, self.color, self.mode)
                selected.add(n)
            else:
                self._set_pad(n, *base_pads[n])
                if n in notes:
                    selected.discard(n)
        self.selected = selected
        self._changed()

    def _pad_release(self, moved=False):
        self._drag_action = None
        if self.undo_stack and self.undo_stack[-1] == tuple(self.pads):
            self.undo_stack.pop()  # nothing actually changed

    def _pad_pick(self, note):
        vel, mode = self.pads[note]
        self.color = vel
        if vel:
            self.mode = mode
        self._refresh_info()
        self._flash_hint(t("picked", colour=colour_name(vel), mode=mode_long(self.mode)))

    def _paint_notes(self, notes, additive=False):
        """Row / column / all selectors: colour and mark these pads (or unmark if all are marked)."""
        notes = list(notes)
        if all(n in self.selected for n in notes):
            self.selected.difference_update(notes)
            self._changed()
            return
        self._snapshot()
        if not additive:
            self.selected = set()
        for n in notes:
            self.selected.add(n)
            self._set_pad(n, self.color, self.mode)
        self._changed()

    def _select_row(self, row, additive=False):
        self._paint_notes(range(row * 8, row * 8 + 8), additive)

    def _select_col(self, col, additive=False):
        self._paint_notes(range(col, 64, 8), additive)

    def _select_all_toggle(self, additive=False):
        self._paint_notes(range(64), additive)

    def select_all(self):
        # Mark everything without changing colours.
        self.selected = set(range(64))
        self._changed()

    def clear_selection(self):
        if self.selected:
            self.selected.clear()
            self._changed()

    def _apply_to_selection(self, color=None, mode=None):
        """New colour -> marked pads keep their mode; new mode -> they keep their colour."""
        if not self.selected:
            return
        new = {n: (self.pads[n][0] if color is None else color,
                   self.pads[n][1] if mode is None else mode) for n in self.selected}
        if all(self.pads[n] == v for n, v in new.items()):
            return
        self._snapshot()
        for n, (v, m) in new.items():
            self._set_pad(n, v, m)
        self._changed()

    def set_color(self, vel):
        self.color = vel
        self.storage.settings["color"] = vel
        self._apply_to_selection(color=vel)
        self._refresh_info()

    def set_mode(self, mode):
        self.mode = mode
        self.storage.settings["mode"] = mode
        self._apply_to_selection(mode=mode)
        self._refresh_info()

    def turn_off_selected(self):
        if not self.selected:
            return
        self._snapshot()
        for n in self.selected:
            self._set_pad(n, 0, self.pads[n][1])
        self._changed()

    def turn_off_all(self):
        if all(v == 0 for v, _ in self.pads):
            return
        self.storage.push_history(tuple(self.pads), self.layout_name)
        self._snapshot()
        for n in range(64):
            self._set_pad(n, 0, self.pads[n][1])
        self.selected.clear()
        self._changed()
        self._refresh_lists()

    def undo(self):
        if not self.undo_stack:
            return
        self.redo_stack.append(tuple(self.pads))
        self._restore(self.undo_stack.pop())

    def redo(self):
        if not self.redo_stack:
            return
        self.undo_stack.append(tuple(self.pads))
        self._restore(self.redo_stack.pop())

    def _restore(self, pads):
        for n, (v, m) in enumerate(pads):
            self._set_pad(n, v, m)
        self._changed()

    # ------------------------------------------------------------ layouts
    def load_layout(self, pads, name):
        pads = tuple(pads)
        current = tuple(self.pads)
        if pads != current:
            self.storage.push_history(current, self.layout_name)
            self._snapshot()
        self.pads = list(pads)
        self.selected.clear()
        self.layout_name = name or ""
        self.layout_base = pads
        self.sent = [None] * 64  # loading always sends the complete layout
        self._pending_notes.update(range(64))
        self._changed()
        self._refresh_lists()

    def load_path(self, path):
        try:
            pads, name = load_file(path)
        except (OSError, ValueError) as exc:
            messagebox.showerror(t("open_failed"), "%s\n\n%s" % (path, exc), parent=self)
            return
        self.load_layout(pads, name)

    def open_file(self):
        path = filedialog.askopenfilename(
            parent=self, title=t("open_title"),
            filetypes=[("MIDI RGB Layout", "*" + EXTENSION), (t("all_files"), "*.*")],
            initialdir=self.storage.get("last_dir") or os.path.expanduser("~"))
        if path:
            self.storage.set("last_dir", os.path.dirname(path))
            self.load_path(path)

    def export_file(self, pads=None, name=None):
        pads = tuple(self.pads) if pads is None else pads
        name = name if name is not None else (self.layout_name or "Layout")
        path = filedialog.asksaveasfilename(
            parent=self, title=t("export_title"), defaultextension=EXTENSION,
            initialfile=(name or "Layout") + EXTENSION,
            filetypes=[("MIDI RGB Layout", "*" + EXTENSION)],
            initialdir=self.storage.get("last_dir") or os.path.expanduser("~"))
        if not path:
            return
        try:
            save_file(path, pads, name)
            self.storage.set("last_dir", os.path.dirname(path))
            self._flash_hint(t("exported", name=os.path.basename(path)))
        except OSError as exc:
            messagebox.showerror(t("export_failed"), str(exc), parent=self)

    def _ask_name(self, title, text, initial=""):
        dialog = ctk.CTkInputDialog(title=title, text=text, fg_color=PANEL, button_fg_color=ACCENT,
                                    button_hover_color=ACCENT_HOVER, entry_fg_color=CARD,
                                    entry_border_color=BORDER)
        if initial:
            dialog.after(150, lambda: (dialog._entry.insert(0, initial),
                                       dialog._entry.select_range(0, "end")))
        value = dialog.get_input()
        return value.strip() if value else None

    def save_to_library(self, pads=None, name=None):
        pads = tuple(self.pads) if pads is None else tuple(pads)
        suggestion = name if name is not None else self.layout_name
        if suggestion in PRESET_NAMES:
            suggestion = ""
        name = self._ask_name(t("save_title"), t("name_prompt"), suggestion)
        if not name:
            return
        path = self.storage.library_path(name)
        if os.path.exists(path) and not messagebox.askyesno(
                t("overwrite_q"), t("exists_msg", name=name), parent=self):
            return
        try:
            self.storage.save_to_library(name, pads)
        except OSError as exc:
            messagebox.showerror(t("save_failed"), str(exc), parent=self)
            return
        if pads == tuple(self.pads):
            self.layout_name = name
            self.layout_base = pads
            self._refresh_info()
            self._schedule_autosave()
        self._refresh_lists()
        self._flash_hint(t("saved", name=name))

    def _overwrite_library(self, it):
        if not messagebox.askyesno(t("overwrite_q"), t("overwrite_msg", name=it.name), parent=self):
            return
        self.storage.save_to_library(it.name, tuple(self.pads))
        self.layout_name = it.name
        self.layout_base = tuple(self.pads)
        self._refresh_info()
        self._refresh_lists()

    def _rename_library(self, it):
        name = self._ask_name(t("rename_title"), t("new_name"), it.name)
        if not name or name == it.name:
            return
        if os.path.exists(self.storage.library_path(name)) and not messagebox.askyesno(
                t("overwrite_q"), t("exists_msg", name=name), parent=self):
            return
        self.storage.rename_in_library(it, name)
        if self.layout_name == it.name:
            self.layout_name = name
            self._refresh_info()
        self._refresh_lists()

    def _delete_library(self, it):
        if messagebox.askyesno(t("delete_q"), t("delete_msg", name=it.name), parent=self):
            try:
                self.storage.delete_from_library(it)
            except OSError as exc:
                messagebox.showerror(t("delete_failed"), str(exc), parent=self)
            self._refresh_lists()

    def _clear_history(self):
        if messagebox.askyesno(t("clear_history_q"), t("clear_history_msg"), parent=self):
            self.storage.clear_history()
            self._refresh_lists()

    def save_as_standard(self):
        if not messagebox.askyesno(t("save_default_q"), t("save_default_msg"), parent=self):
            return
        self.storage.save_standard(tuple(self.pads))
        self.layout_name = t("preset_default")
        self.layout_base = tuple(self.pads)
        self._refresh_info()
        self._refresh_lists()
        self._schedule_autosave()

    def reset_standard(self):
        if not self.storage.has_custom_standard():
            self._flash_hint(t("default_is_builtin"))
            return
        if messagebox.askyesno(t("reset_default_q"), t("reset_default_msg"), parent=self):
            self.storage.reset_standard()
            self._refresh_lists()

    # ------------------------------------------------------------ info / hints
    def _refresh_all(self):
        self.matrix.set_state(self.pads, self.selected)
        self._refresh_info()

    def _cfg(self, widget, **kw):
        """configure() only when something changed (customtkinter redraws on every call)."""
        key = id(widget)
        if self._cfg_cache.get(key) != kw:
            self._cfg_cache[key] = kw
            widget.configure(**kw)

    def _refresh_info(self):
        hexc = VELOCITY_HEX[self.color] if self.color else "#2A2C33"
        self.current_chip.itemconfigure(self._chip, fill=hexc)
        self._cfg(self.current_name, text=colour_name(self.color) if self.color else t("off_black"))
        self._cfg(self.current_mode, text=t("colour_value", mode=mode_long(self.mode), n=self.color))
        if self.basic_grid.selected != self.color:
            self.basic_grid.set_selected(self.color)
        if self.all_grid.selected != self.color:
            self.all_grid.set_selected(self.color)
        if self._shown_mode != self.mode:
            self._shown_mode = self.mode
            group = MODES[self.mode][0]
            for g, (seg, channels, labels) in self.mode_buttons.items():
                seg.set(labels[channels.index(self.mode)] if g == group else "")
        self._cfg(self.title_label, text=self.layout_name or t("untitled"))
        modified = self.layout_base is not None and tuple(self.pads) != self.layout_base
        self._cfg(self.modified_label, text=t("modified") if modified or self.layout_base is None else "")
        n = len(self.selected)
        marked = "" if not n else (t("marked_one") if n == 1 else t("marked_many", n=n))
        self._cfg(self.selection_label, text=marked)
        self._cfg(self.btn_undo, state="normal" if self.undo_stack else "disabled")
        self._cfg(self.btn_redo, state="normal" if self.redo_stack else "disabled")
        self._update_list_highlight()
        if not self._hint_flash:
            self._set_default_hint()

    def _set_default_hint(self):
        self._cfg(self.hint_label, text=t("hint"))

    def _pad_hover(self, note):
        if self._hint_flash:
            return
        if note is None:
            self._set_default_hint()
            return
        vel, mode = self.pads[note]
        text = t("pad_hover", n=note, colour=colour_name(vel) if vel else t("off"))
        if vel:
            text += "  ·  " + mode_long(mode)
        self._cfg(self.hint_label, text=text)

    def _swatch_hover(self, vel):
        if vel is None:
            self._set_default_hint()
        else:
            self._cfg(self.hint_label, text=t("swatch_hover", colour=colour_name(vel), n=vel))

    def _flash_hint(self, text):
        if self._hint_flash:
            self.after_cancel(self._hint_flash)
        self._cfg(self.hint_label, text=text, text_color=TEXT)

        def done():
            self._hint_flash = None
            self._cfg(self.hint_label, text=t("hint"), text_color=MUTED)

        self._hint_flash = self.after(2500, done)

    # ------------------------------------------------------------ MIDI
    def _schedule_flush(self):
        if self._flush_job is None:
            self._flush_job = self.after(10, self._flush)

    def _flush(self):
        self._flush_job = None
        notes = sorted(n for n in self._pending_notes if self.sent[n] != self.pads[n])
        self._pending_notes.clear()
        if not notes or not self.link.target:
            return
        if not self._device_present and not self.link.is_present():
            # Not connected right now - everything is sent once it shows up.
            self.sent = [None] * 64
            return
        ok = self.link.send_pads([(n, self.pads[n][0], self.pads[n][1]) for n in notes])
        if ok:
            for n in notes:
                self.sent[n] = self.pads[n]
        else:
            self.sent = [None] * 64
        self._update_status()

    def resend_all(self):
        self.sent = [None] * 64
        self._pending_notes.update(range(64))
        self._flush()
        if self.link.error is None and self._device_present:
            self._flash_hint(t("resent"))

    def _poll_devices(self):
        try:
            names = self.link.port_names()
            self._update_device_values(names)
            present = self.link.is_present(names)
            if present and (not self._device_present or None in self.sent):
                # Device (re)appeared, app started, or an earlier send failed:
                # send the complete current state.
                self._device_present = True
                self.sent = [None] * 64
                self._pending_notes.update(range(64))
                self._flush()
            self._device_present = present
            self._update_status()
        finally:
            self.after(POLL_MS, self._poll_devices)

    def _update_device_values(self, names):
        if names != self._port_names:
            self._port_names = names
            self.device_menu.configure(values=[t("no_device")] + list(names))

    def _update_status(self):
        idx, full = self.link.find_port(self._port_names or [])
        target = self.link.target
        shown = full if full else (t("disconnected", name=target) if target else t("no_device"))
        if self._cfg_cache.get("device_shown") != shown:
            self._cfg_cache["device_shown"] = shown
            self.device_menu.set(shown)
        if not self.link.available:
            colour, text = DANGER, t("st_midi_unavailable")
        elif not target:
            colour, text = MUTED, t("st_no_device")
        elif full is None:
            colour, text = MUTED, t("st_waiting")
        elif self.link.error:
            colour, text = WARN, t("err_" + self.link.error) if ("err_" + self.link.error) in S else self.link.error
        else:
            colour, text = OK, t("st_connected")
        self.status_dot.itemconfigure(self._dot, fill=colour)
        self._cfg(self.status_label, text=text, text_color=MUTED if colour in (MUTED, OK) else colour)

    def _on_device_chosen(self, name):
        if name == t("no_device"):
            # Deliberately no device: close the port (nothing is sent) and remember the choice.
            self.link.set_target(None)
            self.link.error = None
            self.storage.set("device", "")
            self._device_present = False
            self._update_status()
            return
        self.link.set_target(name)
        self.link.error = None
        self.storage.set("device", normalize(name))
        self._device_present = False  # triggers a full send on the next poll
        self.after(10, self._poll_now)

    def _poll_now(self):
        names = self.link.port_names()
        self._update_device_values(names)
        if self.link.is_present(names):
            self._device_present = True
            self.resend_all()
        self._update_status()

    def _toggle_release(self):
        self.link.release_port = bool(self._release_var.get())
        self.storage.set("release_port", self.link.release_port)
        if self.link.release_port:
            self.link.close()

    # ------------------------------------------------------------ persistence
    def _schedule_autosave(self):
        if self._autosave_job is not None:
            self.after_cancel(self._autosave_job)
        self._autosave_job = self.after(AUTOSAVE_MS, self._autosave)

    def _autosave(self):
        self._autosave_job = None
        try:
            self.storage.save_current(tuple(self.pads), self.layout_name)
            self.storage.settings["base_name"] = self.layout_name
            self.storage.settings["base_clean"] = (self.layout_base is not None
                                                   and tuple(self.pads) == self.layout_base)
            self.storage.save_settings()
        except OSError as exc:
            self._flash_hint(t("autosave_failed", err=exc))

    def _on_close(self):
        # Save everything, then just close. Nothing is sent to the controller,
        # so the pads keep their colours while it has power.
        try:
            if self._autosave_job is not None:
                self.after_cancel(self._autosave_job)
            self._autosave()
            self.storage.push_history(tuple(self.pads), self.layout_name)
            if self.state() == "normal":
                self.storage.settings["geometry"] = self.geometry()
            self.storage.save_settings()
        finally:
            self.link.shutdown()
            self.destroy()

    # ------------------------------------------------------------ misc
    def _set_icon(self):
        if IS_MAC:
            return  # macOS uses the icon of the .app bundle
        try:
            self._icon = tk.PhotoImage(file=os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.png"))
            self._iconbitmap_method_called = True  # keep customtkinter from replacing our icon
            self.iconphoto(True, self._icon)
        except (tk.TclError, OSError):
            pass

    def open_data_dir(self):
        path = self.storage.dir
        try:
            if sys.platform.startswith("win"):
                os.startfile(path)  # noqa: S606
            elif IS_MAC:
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except OSError:
            messagebox.showinfo(t("data_dir"), path, parent=self)

    def show_about(self):
        messagebox.showinfo(t("about_title"), t("about", app=APP_NAME, version=VERSION, author=AUTHOR,
                                                dir=self.storage.dir), parent=self)

    def show_licenses(self):
        """Own license plus the licenses of all bundled third-party components."""
        here = os.path.dirname(os.path.abspath(__file__))
        root = os.path.dirname(here)
        texts = []
        for candidates in ((os.path.join(here, "LICENSE.txt"), os.path.join(root, "LICENSE")),
                           (os.path.join(here, "THIRD_PARTY_NOTICES.txt"),
                            os.path.join(root, "THIRD_PARTY_LICENSES.md"))):
            for path in candidates:
                if os.path.isfile(path):
                    with open(path, encoding="utf-8") as fh:
                        texts.append(fh.read())
                    break
        win = ctk.CTkToplevel(self, fg_color=PANEL)
        win.title(t("licenses_title"))
        win.geometry("760x620")
        win.transient(self)
        box = ctk.CTkTextbox(win, fg_color=CARD, text_color=TEXT, wrap="word",
                             font=ctk.CTkFont(family="Courier", size=12))
        box.pack(fill="both", expand=True, padx=12, pady=12)
        box.insert("1.0", ("\n\n" + "#" * 78 + "\n\n").join(texts) or t("no_licenses"))
        box.configure(state="disabled")
        win.after(100, win.lift)

    def report_callback_exception(self, exc, val, tb):
        text = "".join(traceback.format_exception(exc, val, tb))
        try:
            with open(os.path.join(self.storage.dir, "error.log"), "a", encoding="utf-8") as fh:
                fh.write("\n[%s]\n%s" % (datetime.now().isoformat(timespec="seconds"), text))
        except OSError:
            pass
        sys.stderr.write(text)
        try:
            self._flash_hint(t("unexpected_error"))
        except Exception:
            pass


def main():
    path = None
    for arg in sys.argv[1:]:
        if arg.lower().endswith(EXTENSION) and os.path.isfile(arg):
            path = arg
    app = App(open_path=path)
    smoke = os.environ.get("APC_RGB_SMOKE_TEST")
    if smoke:
        # Used by the build pipeline: start, autosave, close again
        # ("screenshot": also mark a few pads and report the window position).
        if smoke == "screenshot":
            app.after(1500, _prepare_screenshot, app)
        app.after(8000 if smoke == "screenshot" else 4000, app._on_close)
    app.mainloop()


def _prepare_screenshot(app):
    import json

    app.selected = {41, 42, 43, 49, 50, 51}
    app._changed()
    # fit the window on the (small) screen of the build machine
    width = min(1240, app.winfo_screenwidth() - 40)
    height = min(800, app.winfo_screenheight() - 90)
    app.geometry("%dx%d+20+40" % (width, height))
    app.update()
    app.lift()
    app.attributes("-topmost", True)
    app.update()
    info = {"x": app.winfo_rootx(), "y": app.winfo_rooty(), "w": app.winfo_width(),
            "h": app.winfo_height(), "screen_w": app.winfo_screenwidth()}
    with open(os.path.join(app.storage.dir, "window.json"), "w", encoding="utf-8") as fh:
        json.dump(info, fh)


if __name__ == "__main__":
    main()
