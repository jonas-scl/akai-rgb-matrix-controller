"""User interface texts (English and German).

The language follows the operating system (German systems get German, everything
else English) and can be changed in the ••• menu.
"""

import locale
import os
import subprocess
import sys

LANGUAGES = [("en", "English"), ("de", "Deutsch")]
_lang = "en"

S = {
    # header / device
    "no_device": ("No MIDI device", "Kein MIDI-Gerät"),
    "resend": ("Send again", "Neu senden"),
    "disconnected": ("{name}  (disconnected)", "{name}  (getrennt)"),
    "st_midi_unavailable": ("MIDI system not available", "MIDI-System nicht verfügbar"),
    "st_no_device": ("No device selected – nothing is sent", "Kein Gerät gewählt – es wird nichts gesendet"),
    "st_waiting": ("Not connected – waiting for device", "Nicht verbunden – wartet auf Gerät"),
    "st_connected": ("Connected", "Verbunden"),
    "err_not_found": ("Device not found", "Gerät nicht gefunden"),
    "err_busy": ("Port busy or not reachable", "Port belegt oder nicht erreichbar"),
    "err_send_failed": ("Sending failed", "Senden fehlgeschlagen"),
    # sidebar
    "save": ("Save …", "Speichern …"),
    "as_default": ("Set as default", "Als Standard"),
    "templates": ("Templates", "Vorlagen"),
    "preset_default": ("Default", "Standard"),
    "preset_test": ("Colour test", "Farbtest"),
    "default_custom": ("your own version", "eigene Version"),
    "default_builtin": ("built-in", "Vorgabe"),
    "test_sub": ("test pattern, built-in", "Testbild, fest hinterlegt"),
    "my_layouts": ("My layouts", "Meine Layouts"),
    "new": ("+ New", "+ Neu"),
    "nothing_saved": ("Nothing saved yet.", "Noch nichts gespeichert."),
    "recent": ("Recently used", "Zuletzt verwendet"),
    "clear": ("Clear", "Leeren"),
    "empty": ("Empty so far.", "Noch leer."),
    "untitled": ("Untitled", "Ohne Namen"),
    "just_now": ("just now", "gerade eben"),
    "min_ago": ("{n} min ago", "vor {n} Min."),
    "today_at": ("today, {time}", "heute, {time}"),
    "date_fmt": ("%Y-%m-%d, %H:%M", "%d.%m.%Y, %H:%M"),
    # centre
    "modified": ("• modified", "• geändert"),
    "marked_one": ("1 pad marked", "1 Pad markiert"),
    "marked_many": ("{n} pads marked", "{n} Pads markiert"),
    "select_all": ("Mark all", "Alle markieren"),
    "clear_selection": ("Unmark", "Markierung aufheben"),
    "turn_off_selected": ("Turn marked off", "Markierte aus"),
    "undo": ("Undo", "Rückgängig"),
    "redo": ("Redo", "Wiederholen"),
    "all_off": ("All off", "Alles aus"),
    "all": ("All", "Alle"),
    "hint": ("Drag a box: several pads  ·  Shift: add  ·  Right-click: pick colour  ·  Esc: unmark",
             "Rahmen: mehrere Pads  ·  Shift: ergänzen  ·  Rechtsklick: Farbe übernehmen  ·  Esc: Markierung weg"),
    "pad_hover": ("Pad {n}  ·  {colour}", "Pad {n}  ·  {colour}"),
    "off": ("off", "aus"),
    "picked": ("Colour picked: {colour} · {mode}", "Farbe übernommen: {colour} · {mode}"),
    "resent": ("All 64 pads were sent again.", "Alle 64 Pads wurden neu gesendet."),
    # right panel
    "colour": ("Colour", "Farbe"),
    "mode": ("Mode", "Modus"),
    "brightness_pct": ("Brightness (%)", "Helligkeit (%)"),
    "pulse": ("Pulse", "Pulsieren"),
    "blink": ("Blink", "Blinken"),
    "more_colours": ("+  All 128 colours", "+  Alle 128 Farben"),
    "fewer_colours": ("–  Fewer colours", "–  Weniger Farben"),
    "off_black": ("Off (black)", "Aus (schwarz)"),
    "colour_value": ("{mode}  ·  colour value {n}", "{mode}  ·  Farbwert {n}"),
    "swatch_hover": ("{colour}  ·  colour value {n}", "{colour}  ·  Farbwert {n}"),
    "help": ("Click a pad or drag a box over several pads: they get the current colour and are "
             "marked. A new colour or mode then applies to all marked pads. A new click or box "
             "starts a new marking, hold Shift to add to it. Right-click a pad to pick up its colour.",
             "Pad anklicken oder einen Rahmen über mehrere Pads ziehen: Sie bekommen die aktuelle "
             "Farbe und werden markiert. Eine neue Farbe bzw. ein neuer Modus gilt dann für alle "
             "markierten Pads. Ein neuer Klick oder Rahmen startet eine neue Markierung, mit Shift "
             "wird ergänzt. Rechtsklick auf ein Pad übernimmt dessen Farbe."),
    "mode_brightness": ("Brightness {v}", "Helligkeit {v}"),
    "mode_pulse": ("Pulse {v}", "Pulsieren {v}"),
    "mode_blink": ("Blink {v}", "Blinken {v}"),
    "colour_n": ("Colour {n}", "Farbe {n}"),
    # menus
    "m_load": ("Load", "Laden"),
    "m_save_default": ("Save current pads as default", "Aktuelle Pads als Standard speichern"),
    "m_reset_default": ("Reset default to built-in", "Standard auf Vorgabe zurücksetzen"),
    "m_overwrite": ("Overwrite with current pads", "Mit aktuellen Pads überschreiben"),
    "m_rename": ("Rename …", "Umbenennen …"),
    "m_export": ("Export …", "Exportieren …"),
    "m_delete": ("Delete", "Löschen"),
    "m_save_to_lib": ("Save to “My layouts” …", "In „Meine Layouts“ speichern …"),
    "m_remove_history": ("Remove from history", "Aus Verlauf entfernen"),
    "m_open": ("Open …", "Öffnen …"),
    "m_resend": ("Send everything to the device again", "Alles neu an das Gerät senden"),
    "m_release": ("Release MIDI port after sending (recommended)",
                  "MIDI-Port nach dem Senden freigeben (empfohlen)"),
    "m_language": ("Language", "Sprache"),
    "m_data_dir": ("Open data folder", "Datenordner öffnen"),
    "m_licenses": ("Licenses …", "Lizenzen …"),
    "m_about": ("About …", "Über …"),
    "mod_ctrl": ("Ctrl+", "Strg+"),
    # dialogs
    "open_failed": ("Opening failed", "Öffnen fehlgeschlagen"),
    "open_title": ("Open layout", "Layout öffnen"),
    "all_files": ("All files", "Alle Dateien"),
    "export_title": ("Export layout", "Layout exportieren"),
    "exported": ("Exported: {name}", "Exportiert: {name}"),
    "export_failed": ("Export failed", "Exportieren fehlgeschlagen"),
    "save_title": ("Save layout", "Layout speichern"),
    "name_prompt": ("Name of the layout:", "Name für das Layout:"),
    "overwrite_q": ("Overwrite?", "Überschreiben?"),
    "exists_msg": ("“{name}” already exists. Overwrite it?", "„{name}“ gibt es schon. Überschreiben?"),
    "save_failed": ("Saving failed", "Speichern fehlgeschlagen"),
    "saved": ("Saved: {name}", "Gespeichert: {name}"),
    "overwrite_msg": ("Overwrite “{name}” with the current pads?",
                      "„{name}“ mit den aktuellen Pads überschreiben?"),
    "rename_title": ("Rename", "Umbenennen"),
    "new_name": ("New name:", "Neuer Name:"),
    "delete_q": ("Delete?", "Löschen?"),
    "delete_msg": ("Really delete “{name}”?", "„{name}“ wirklich löschen?"),
    "delete_failed": ("Deleting failed", "Löschen fehlgeschlagen"),
    "clear_history_q": ("Clear history?", "Verlauf leeren?"),
    "clear_history_msg": ("Clear “Recently used”?", "„Zuletzt verwendet“ leeren?"),
    "save_default_q": ("Set as default?", "Als Standard speichern?"),
    "save_default_msg": ("The current pads become the new default.",
                         "Die aktuellen Pads werden zum neuen Standard."),
    "default_is_builtin": ("The default is already the built-in one.", "Standard ist bereits die Vorgabe."),
    "reset_default_q": ("Reset default?", "Standard zurücksetzen?"),
    "reset_default_msg": ("Your own default is deleted and the built-in one restored.",
                          "Deine eigene Standard-Version wird gelöscht und die Vorgabe wiederhergestellt."),
    "autosave_failed": ("Autosave failed: {err}", "Automatisches Speichern fehlgeschlagen: {err}"),
    "unexpected_error": ("Unexpected error (details in error.log in the data folder)",
                         "Unerwarteter Fehler (Details in error.log im Datenordner)"),
    "data_dir": ("Data folder", "Datenordner"),
    "about_title": ("About", "Über"),
    "about": ("{app} {version}\n\nRGB colours for the Akai APC mini mk2.\n\n"
              "© 2026 {author}. Licensed under the PolyForm Shield License 1.0.0 "
              "(••• → Licenses). No warranty.\n\n"
              "Akai, APC and APC mini are trademarks of their respective owners; "
              "this project is not affiliated with them.\n\nData folder:\n{dir}",
              "{app} {version}\n\nRGB-Steuerung für das Akai APC mini mk2.\n\n"
              "© 2026 {author}. Lizenz: PolyForm Shield License 1.0.0 "
              "(••• → Lizenzen). Ohne Gewähr.\n\n"
              "Akai, APC und APC mini sind Marken ihrer Inhaber; keine Verbindung zu diesen.\n\n"
              "Datenordner:\n{dir}"),
    "licenses_title": ("Licenses", "Lizenzen"),
    "no_licenses": ("No license texts found.", "Keine Lizenztexte gefunden."),
}

COLOUR_NAMES = {
    0: ("Off", "Aus"), 3: ("White", "Weiß"), 5: ("Red", "Rot"), 9: ("Orange", "Orange"),
    13: ("Yellow", "Gelb"), 16: ("Light green", "Hellgrün"), 21: ("Green", "Grün"),
    24: ("Turquoise", "Türkis"), 44: ("Light blue", "Hellblau"), 45: ("Blue", "Blau"),
    52: ("Purple", "Lila"), 53: ("Pink", "Pink"),
}


def _index():
    return 1 if _lang == "de" else 0


def t(key, **kw):
    text = S[key][_index()]
    return text.format(**kw) if kw else text


def colour_name(vel):
    if vel in COLOUR_NAMES:
        return COLOUR_NAMES[vel][_index()]
    return t("colour_n", n=vel)


def language():
    return _lang


def set_language(code):
    global _lang
    _lang = code if code in dict(LANGUAGES) else "en"


def system_language():
    """'de' if the operating system is set to German, otherwise 'en'."""
    code = ""
    try:
        if sys.platform.startswith("win"):
            import ctypes

            langid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
            return "de" if (langid & 0x3FF) == 0x07 else "en"
        if sys.platform == "darwin":
            out = subprocess.run(["defaults", "read", "-g", "AppleLanguages"], capture_output=True,
                                 text=True, timeout=2).stdout
            first = out.replace("(", "").replace('"', "").strip().split(",")[0].strip()
            return "de" if first.lower().startswith("de") else "en"
        code = os.environ.get("LC_ALL") or os.environ.get("LC_MESSAGES") or os.environ.get("LANG") or ""
        if not code:
            code = locale.getlocale()[0] or ""
    except Exception:
        return "en"
    return "de" if code.lower().startswith("de") else "en"
