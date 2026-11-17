"""Original small keycode catalogue; no VIA application code or tables reused.

Basic keys use USB HID Keyboard/Keypad usage IDs. Extended assignments are
limited to the observed layer range and identified GMK104 media/control keys.
"""
KEYCODES = {0: "Disabled", 1: "Transparent (fall through)"}
KEYCODES.update({4 + i: chr(65 + i) for i in range(26)})
KEYCODES.update({30 + i: str((i + 1) % 10) for i in range(10)})
KEYCODES.update(dict(enumerate((
    "Enter", "Esc", "Backspace", "Tab", "Space", "-", "=", "[", "]", "\\",
    "Non-US #", ";", "'", "`", ",", ".", "/", "Caps Lock",
), 40)))
KEYCODES.update({58 + i: f"F{i + 1}" for i in range(12)})
KEYCODES.update(dict(enumerate((
    "Print Screen", "Scroll Lock", "Pause", "Insert", "Home", "Page Up",
    "Delete", "End", "Page Down", "Right", "Left", "Down", "Up", "Num Lock",
    "Numpad /", "Numpad *", "Numpad -", "Numpad +", "Numpad Enter",
    "Numpad 1", "Numpad 2", "Numpad 3", "Numpad 4", "Numpad 5", "Numpad 6",
    "Numpad 7", "Numpad 8", "Numpad 9", "Numpad 0", "Numpad .",
    "Non-US \\", "Application", "Power", "Numpad =",
), 70)))
KEYCODES.update({104 + i: f"F{i + 13}" for i in range(12)})
KEYCODES.update(dict(enumerate((
    "Left Ctrl", "Left Shift", "Left Alt", "Left Super",
    "Right Ctrl", "Right Shift", "Right Alt", "Right Super",
), 224)))
KEYCODES.update({0x5100 + i: f"MO({i}) — hold for layer {i}" for i in range(4)})
# Function/value facts checked against the manual, vendor matrix definition
# and live GMK104 buffers. These are not raw USB keyboard-page usages.
KEYCODES.update({
    0x00A8: "Mute", 0x00A9: "Volume up", 0x00AA: "Volume down",
    0x7820: "Backlight toggle", 0x7F09: "LCD toggle",
})
# Power is intentionally not offered by the picker.
ASSIGNABLE = {code: name for code, name in KEYCODES.items() if code != 102}

# Display-only interpretations: identify existing values without enabling new,
# untested assignments. Numeric values are protocol facts, not copied tables.
MEDIA_LABELS = {
    0x00AB: "Next track", 0x00AC: "Previous track", 0x00AE: "Play / pause",
    0x00B1: "Open mail", 0x00B2: "Calculator",
    0x00B4: "Web search", 0x00B5: "Browser home",
}
LIGHTING_LABELS = {
    0x7821: "Next backlight effect",
    0x7823: "Backlight hue up", 0x7824: "Backlight hue down",
    0x7825: "Backlight saturation up", 0x7826: "Backlight saturation down",
    0x7827: "Backlight brightness up", 0x7828: "Backlight brightness down",
    0x7829: "Backlight speed up", 0x782A: "Backlight speed down",
}
VENDOR_LABELS = {
    0x7F00: "2.4 GHz mode", 0x7F01: "Bluetooth slot 1",
    0x7F02: "Bluetooth slot 2", 0x7F03: "Bluetooth slot 3",
    0x7F04: "Windows key lock", 0x7F07: "Key scan delay",
    0x7F0C: "LCD profile", 0x5F88: "Windows / macOS mode",
}
KEYCODES.update(MEDIA_LABELS)
KEYCODES.update(LIGHTING_LABELS)
KEYCODES.update(VENDOR_LABELS)
KEYCODES[0x5221] = "MO(1) — newer keycode range"
KEYCODES[0x0087] = "International key 1"


def is_identified(code):
    return code in KEYCODES or code in (0x7C00, 0x5C00)


def explanation(code):
    if code == 0xFFFF:
        return ("Unresolved firmware value. Its action has not been verified; do not assume "
                "transparent, disabled, or reset. Preserved exactly unless explicitly replaced.")
    if code in VENDOR_LABELS:
        return ("Interpretation from the vendor's custom-function list and observed keycode "
                "family. Behavior is not hardware-tested here; shown for identification only.")
    if code in LIGHTING_LABELS:
        return ("Interpretation of the observed 0x782x lighting family, consistent with Fn "
                "shortcuts in the manual. Shown for identification only; behavior is not tested.")
    if code in MEDIA_LABELS:
        return ("Standard QMK media-code interpretation of the stored value. "
                "Shown for identification only; behavior is not tested here.")
    if code == 0x5221:
        return ("MO(1) in the newer QMK range. This firmware also stores legacy 0x5101; "
                "do not convert between them. This interpretation is not hardware-verified.")
    if not is_identified(code):
        return "Unidentified firmware keycode. Preserved exactly unless explicitly replaced."
    return ""


def describe(code):
    if code in (0x7C00, 0x5C00):
        return f"Bootloader / reset [0x{code:04X}]"
    return KEYCODES.get(code, f"Unknown 0x{code:04X} (preserved)")


def short_name(code):
    if code == 1:
        return "▽"
    if code == 0:
        return "—"
    if 0x5100 <= code <= 0x5103:
        return f"MO({code - 0x5100})"
    if code == 0x5221:
        return "MO(1)*"
    if code not in KEYCODES:
        return f"0x{code:04X}"
    name = KEYCODES[code]
    return {
        "Backlight toggle": "Light", "LCD toggle": "LCD",
        "Next track": "Next", "Previous track": "Prev", "Play / pause": "Play",
        "Open mail": "Mail", "Calculator": "Calc", "Web search": "Search",
        "Browser home": "Web",
        "Next backlight effect": "RGB FX",
        "Backlight hue up": "Hue +", "Backlight hue down": "Hue −",
        "Backlight saturation up": "Sat +", "Backlight saturation down": "Sat −",
        "Backlight brightness up": "Bri +", "Backlight brightness down": "Bri −",
        "Backlight speed up": "Spd +", "Backlight speed down": "Spd −",
        "2.4 GHz mode": "2.4G", "Bluetooth slot 1": "BT 1",
        "Bluetooth slot 2": "BT 2", "Bluetooth slot 3": "BT 3",
        "Windows key lock": "Win lock", "Key scan delay": "Scan",
        "LCD profile": "LCD mode", "Windows / macOS mode": "Win/Mac",
        "Volume up": "Vol +", "Volume down": "Vol −",
        "Backspace": "Bksp", "Print Screen": "PrtSc", "Scroll Lock": "ScrLk",
        "Page Up": "PgUp", "Page Down": "PgDn", "Caps Lock": "Caps",
        "Num Lock": "Num", "Left Ctrl": "L Ctrl", "Right Ctrl": "R Ctrl",
        "Left Shift": "L Shift", "Right Shift": "R Shift",
        "Left Alt": "L Alt", "Right Alt": "R Alt",
        "Left Super": "L Super", "Right Super": "R Super",
        "Non-US #": "ISO #", "Non-US \\": "ISO \\",
    }.get(name, name.replace("Numpad ", "KP "))
