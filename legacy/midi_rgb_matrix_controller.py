#The following code works with Python 3.10.6 and the following packages installed: mido, python-rtmidi
#The following code was written by
#This software is provided as-is, with no warranty
#v1.0

import mido
import tkinter as tk
from tkinter import filedialog, messagebox
import json

# Farbpalette und Kanalkonfiguration
COLOR_PALETTE = {
    "#000000": 0,  # Black
    "#FFFFFF": 3,  # White
    "#FFFF00": 13,  # Yellow
    "#FF7F00": 9,  # Orange
    "#FF0000": 5,  # Red
    "#8B00FF": 52,  # Purple
    "#00FFFF": 24,  # Cyan (Turquoise)
    "#00FF00": 21,  # Green
    "#0000FF": 45,  # Blue
    "#4C4CFF": 44,  # Khaki (Light Yellow)
    "#FF00FF": 53,  # Light Pink
    "#88FF4C": 16  # Light Gray
}

CHANNELS = {
    0: "10% Brightness", 1: "25% Brightness", 2: "50% Brightness", 3: "65% Brightness",
    4: "75% Brightness", 5: "90% Brightness", 6: "100% Brightness", 7: "Pulsing 1/16",
    8: "Pulsing 1/8", 9: "Pulsing 1/4", 10: "Pulsing 1/2", 11: "Blinking 1/24", 12: "Blinking 1/16",
    13: "Blinking 1/8", 14: "Blinking 1/4", 15: "Blinking 1/2"
}
CHANNELS_TO_SHORTCUT = {
    0: "10%", 1: "25%", 2: "50%", 3: "65%",
    4: "75%", 5: "90%", 6: "100%", 7: "P1/16",
    8: "P1/8", 9: "P1/4", 10: "P1/2", 11: "B1/24", 12: "B1/16",
    13: "B1/8", 14: "B1/4", 15: "B1/2"
}

# Globale Variablen
selected_color = "#FFFFFF"
selected_channel = 6
selected_buttons = set()
selected_midi_device = ""
output_port = None

# Funktion: Reset der Matrix
def reset_all():
    try:
        for button in range(64):
            msg = mido.Message('note_on', channel=selected_channel, note=button, velocity=0)
            output_port.send(msg)
    except:
        pass
    selected_buttons.clear()
    for btn in matrix_buttons:
        btn.config(bg=btn.default_color, text="")
        btn.color = btn.default_color
        btn.brightness = 6
    update_ui()
    
def unselect_all():
    selected_buttons.clear()
    update_ui()

# Funktion: MIDI-Nachrichten senden
def send_midi_for_selected():
    for button in selected_buttons:
        color_value = COLOR_PALETTE[selected_color]
        msg = mido.Message('note_on', channel=selected_channel, note=button, velocity=color_value)
        output_port.send(msg)

# Funktionen zum Speichern und Laden
def save_settings():
    settings = {}
    for btn in matrix_buttons:
        settings[btn.button] = {
            "color": btn.color,
            "channel": btn.brightness,
            "device": selected_midi_device
            }
    file_path = filedialog.asksaveasfilename(defaultextension=".midirgb", filetypes=[("MIDI RGB Matrix Controller Files", "*.midirgb")])
    if file_path:
        with open(file_path, 'w') as file:
            json.dump(settings, file)

def load_settings(path=""):
    output_port.close() if output_port else None
    if path == "":
        file_path = filedialog.askopenfilename(filetypes=[("MIDI RGB Matrix Controller Files", "*.midirgb")])
    else:
        file_path = path
    if file_path:
        with open(file_path, 'r') as file:
            settings = json.load(file)
            try:
                change_midi_device(settings["0"]["device"])
            except:    
                print("Device is not connected")
            for btn in matrix_buttons:
                btn.color = settings[str(btn.button)]["color"]
                btn.brightness = settings[str(btn.button)]["channel"]
                if btn.color == "#000000":
                    btn.config(bg=btn.color, text="")
                elif btn.color not in ("#FFFFFF", "#FFFF00", "#00FFFF", "#00FF00", "#88FF4C"):
                    btn.config(bg=btn.color, text=CHANNELS_TO_SHORTCUT[btn.brightness], fg="#FFFFFF")
                else:
                    btn.config(bg=btn.color, text=CHANNELS_TO_SHORTCUT[btn.brightness], fg="#000000")
    file.close()
    selected_buttons.clear()
    resend_from_dict()
    
#Erneutes senden der UI-Matrix
def resend_from_dict():
    global output_port
    for button in list(range(64)):
        for btn in matrix_buttons:
            if btn.button == button:
                color = COLOR_PALETTE[btn.color]
                msg = mido.Message('note_on', channel=btn.brightness, note=btn.button, velocity=color)
                try:
                    output_port.send(msg)
                except:
                    pass
# Funktion: Farbwahl
def select_color(color):
    global selected_color
    selected_color = color
    send_midi_for_selected()
    update_ui()

# Funktion: Kanalwahl
def select_channel(channel):
    global selected_channel
    selected_channel = channel
    send_midi_for_selected()
    update_ui()

# Funktion: Button-Auswahl
def toggle_button(button):
    if button in selected_buttons:
        selected_buttons.remove(button)
    else:
        selected_buttons.add(button)
    send_midi_for_selected()
    update_ui()

# Funktion: UI aktualisieren
def update_ui():
    for idx, color in enumerate(COLOR_PALETTE):
        color_buttons[idx].config(relief="solid" if color == selected_color else "flat")
    for btn in channel_buttons:
        btn.config(relief="solid" if btn.channel == selected_channel else "flat")
    for btn in matrix_buttons:
        if btn.button in selected_buttons:
            btn.brightness = selected_channel
            btn.color = selected_color
            if selected_color == "#000000":
                btn.config(bg=selected_color, text="")
            elif selected_color not in ("#FFFFFF", "#FFFF00", "#00FFFF", "#00FF00", "#88FF4C"):
                btn.config(bg=selected_color, text=CHANNELS_TO_SHORTCUT[btn.brightness], fg="#FFFFFF")
            else:
                btn.config(bg=selected_color, text=CHANNELS_TO_SHORTCUT[btn.brightness], fg="#000000")
    label_device.config(text=f"MIDI-Gerät: {selected_midi_device}")
    scan_midi_devices()

# Funktion: MIDI-Gerät wechseln
def change_midi_device(device):
    try:
        global selected_midi_device, output_port
        selected_midi_device = device
        output_port.close() if output_port else None
        output_port = mido.open_output(selected_midi_device)
        update_ui()
    except:
        output_port = None
        selected_midi_device = ""
        update_ui()

# Lädt das letzte gefundene Midi-Gerät
def load_midi_device():
    global selected_midi_device, output_port
    try:
        selected_midi_device = mido.get_output_names()[-2]
        output_port.close() if output_port else None
        output_port = mido.open_output(selected_midi_device)
        update_ui()
    except:
        output_port = None
        selected_midi_device = ""
        update_ui()

# Funktion: MIDI-Geräte scannen
def scan_midi_devices():
    midi_menu.delete(0, "end")
    for port in mido.get_output_names():
        midi_menu.add_command(
            label=port,
            command=lambda port_name=port: change_midi_device(port_name)
        )
        if port == selected_midi_device:
            midi_menu.entryconfig(midi_menu.index(port), label=f"✓ {port}")
    midi_menu.add_command(label="Geräte scannen", command=scan_midi_devices)

# GUI Setup
root = tk.Tk()
root.title("MIDI RGB Matrix Controller v1.0")

# Menüleiste
menu_bar = tk.Menu(root)
root.config(menu=menu_bar)

file_menu = tk.Menu(menu_bar, tearoff=0)
file_menu.add_command(label="Einstellungen Laden", command=load_settings)
file_menu.add_command(label="Einstellungen Speichern", command=save_settings)
menu_bar.add_cascade(label="Datei", menu=file_menu)

midi_menu = tk.Menu(menu_bar, tearoff=0)
midi_menu.add_command(label="Geräte scannen", command=scan_midi_devices)
menu_bar.add_cascade(label="MIDI", menu=midi_menu)
scan_midi_devices()

help_menu = tk.Menu(menu_bar, tearoff=0)
help_menu.add_command(label="Hilfe")
help_menu.add_command(label="Über", command= lambda: messagebox.showinfo("About",
"""The following code works with Python 3.10.6 and the following packages installed:

mido, python-rtmidi

The following code was written by
jonas-scl (https://github.com/jonas-scl)

This software is provided as-is, with no warranty

v1.0"""))
menu_bar.add_cascade(label="Hilfe", menu=help_menu)

# Label für aktuelles MIDI-Gerät und Taste zum erneuten senden der Midi-Befehle
label_device = tk.Label(root, text=f"MIDI-Gerät: {selected_midi_device}")
label_device.grid(row=0, column=1, sticky="w", padx=5, pady=5)
btn_resend = tk.Button(root, text="   send again   ", command=resend_from_dict)
btn_resend.grid(row=0, column=1, sticky="e", padx=5, pady=5)

# Farbpalette
frame_colors = tk.Frame(root)
frame_colors.grid(row=1, column=1)
color_buttons = []
for idx, color in enumerate(COLOR_PALETTE):
    button = tk.Button(frame_colors, bg=color, width=4, height=2, command=lambda c=color: select_color(c))
    button.grid(row=idx // 3, column=idx % 3)
    color_buttons.append(button)

# Kanalbuttons
frame_channels = tk.Frame(root)
frame_channels.grid(row=2, column=1)
channel_buttons = []
for i in range(16):
    btn = tk.Button(frame_channels, text=CHANNELS[i], command=lambda c=i: select_channel(c))
    btn.channel = i
    btn.grid(row=i // 4, column=i % 4)
    channel_buttons.append(btn)

# 8x8 Matrix
frame_matrix = tk.Frame(root)
frame_matrix.grid(row=1, column=0, rowspan=2)
matrix_buttons = []
for row in range(8):
    for col in range(8):
        button_number = 56 - row * 8 + col  # Berechnung der neuen Nummerierung
        btn = tk.Button(frame_matrix, width=4, height=2, command=lambda b=button_number: toggle_button(b), bg="#000000")
        btn.grid(row=row, column=col)
        btn.button = button_number
        btn.brightness = 6
        btn.color = "#000000"
        btn.default_color = "#000000"
        matrix_buttons.append(btn)

# Reset-Button
btn_reset = tk.Button(root, text="turn off all", command=reset_all)
btn_reset.grid(row=3, column=0, sticky="nsew", padx=5, pady=5)
btn_unselect = tk.Button(root, text="Unselect all", command=unselect_all)
btn_unselect.grid(row=3, column=1, sticky="nsew", padx=5, pady=5)

# UI initialisieren
load_midi_device()
update_ui()
try:
    load_settings("standard.midirgb")
except:
    pass
root.mainloop()