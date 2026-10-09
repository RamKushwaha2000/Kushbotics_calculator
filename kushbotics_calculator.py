#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KUSHBOTICS CALCULATOR  v2.0
Raspberry Pi + ILI9341 320x240 SPI TFT + XPT2046 touch

Flow:  Power ON -> Kushbotics logo -> "Kushbotics Calculator" -> HOME

Screens (all reachable from HOME, every screen has a "< HOME" button):
    Calculator | Scientific | Trigonometry | CAS | Graph | 3D Graph | Settings

Run normally:           python3 kushbotics_calculator.py
Start automatically:    sudo python3 kushbotics_calculator.py --install-autostart
Remove autostart:       sudo python3 kushbotics_calculator.py --uninstall-autostart

Keep kushbotics_logo.png in the same folder as this file.
"""

import glob
import math
import os
import re
import subprocess
import sys
import time

from PIL import Image, ImageDraw, ImageFont

APP_NAME     = "Kushbotics Calculator"
APP_VERSION  = "2.0"
LOGO_FILE    = "kushbotics_logo.png"
SERVICE_NAME = "kushbotics-calculator"
SERVICE_PATH = "/etc/systemd/system/" + SERVICE_NAME + ".service"
SCRIPT_PATH  = os.path.abspath(__file__)
SCRIPT_DIR   = os.path.dirname(SCRIPT_PATH)

# ------------------------------------------------
#  HARDWARE  (created in init_hardware(); settings unchanged)
# ------------------------------------------------
serial    = None
device    = None
spi_touch = None

SW = 320
SH = 240


def init_hardware():
    global serial, device, spi_touch
    from luma.core.interface.serial import spi
    from luma.lcd.device import ili9341
    import spidev

    serial = spi(port=0, device=0, gpio_DC=24, gpio_RST=25, bus_speed_hz=32000000)
    device = ili9341(serial, rotate=0)

    spi_touch = spidev.SpiDev()
    spi_touch.open(0, 1)
    spi_touch.max_speed_hz = 1000000

    if tuple(device.size) != (SW, SH):
        print("WARNING: display size is", device.size, "- expected", (SW, SH))


# ------------------------------------------------
#  HEAVY LIBRARIES (loaded during the startup screen)
# ------------------------------------------------
np = None
sp = None
HAS_NUMPY = False
HAS_SYMPY = False
parse_expr     = None
CAS_TRANSFORMS = None
CAS_LOCALS     = {}


def load_numpy():
    global np, HAS_NUMPY
    try:
        import numpy as _np
        np = _np
        HAS_NUMPY = True
    except Exception:
        HAS_NUMPY = False


def load_sympy():
    global sp, HAS_SYMPY, parse_expr, CAS_TRANSFORMS, CAS_LOCALS
    try:
        import sympy as _sp
        from sympy.parsing.sympy_parser import (
            parse_expr as _parse, standard_transformations,
            implicit_multiplication_application)
        sp = _sp
        parse_expr = _parse
        # implicit multiplication lets "3x", "2sin(x)", "(x+1)(x-1)" work
        CAS_TRANSFORMS = standard_transformations + (implicit_multiplication_application,)
        CAS_LOCALS = {
            "x": sp.Symbol("x"), "t": sp.Symbol("t"), "a": sp.Symbol("a"),
            "k": sp.Symbol("k"), "n": sp.Symbol("n"),
            "pi": sp.pi, "e": sp.E,
            "sin": sp.sin, "cos": sp.cos, "tan": sp.tan,
            "asin": sp.asin, "acos": sp.acos, "atan": sp.atan,
            "sinh": sp.sinh, "cosh": sp.cosh, "tanh": sp.tanh,
            "sqrt": sp.sqrt, "log": sp.log, "exp": sp.exp, "abs": sp.Abs,
        }
        HAS_SYMPY = True
    except Exception:
        HAS_SYMPY = False


# ------------------------------------------------
#  TOUCH CALIBRATION  (UNCHANGED)
# ------------------------------------------------
RAW_X_MIN  = 300
RAW_X_MAX  = 3900
RAW_Y_MIN  = 400
RAW_Y_MAX  = 4095
DEBUG_TOUCH = False

# ------------------------------------------------
#  COLORS
# ------------------------------------------------
C_BG      = (10,  12,  24)
C_DISP    = (18,  20,  38)
C_HEADER  = (14,  18,  40)
C_ACCENT  = (0,   200, 255)
C_BRAND   = (120, 235, 60)

C_NUM     = (28,  32,  60)
C_OP      = (20,  55,  100)
C_FUNC    = (20,  60,  40)
C_TRIG    = (55,  20,  70)
C_CAS     = (70,  40,  10)
C_CLEAR   = (110, 10,  10)
C_EQUAL   = (0,   80,  190)
C_GRAPH   = (0,   80,  60)
C_3DB     = (20,  50,  90)
C_ROT     = (55,  20,  80)
C_HI      = (0,   190, 100)
C_OUTLINE = (45,  55,  95)
C_RANGE   = (60,  40,  0)
C_VAR     = (70,  10,  80)
C_HOMEBTN = (30,  60,  120)
C_ON      = (0,   150, 80)
C_OFF     = (110, 35,  35)
C_NA      = (60,  60,  70)

C_TEXT    = (230, 232, 245)
C_TEXDIM  = (110, 120, 155)
C_EXPR    = (150, 195, 255)
C_RES     = (0,   220, 255)
C_WARN    = (255, 130, 110)

# ------------------------------------------------
#  FONTS  (DejaVu if present, otherwise PIL default)
# ------------------------------------------------
_TTF_BOLD = None
_TTF_REG  = None
for _p in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
           "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf"):
    if os.path.exists(_p):
        _TTF_BOLD = _p
        break
for _p in ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
           "/usr/share/fonts/truetype/freefont/FreeSans.ttf"):
    if os.path.exists(_p):
        _TTF_REG = _p
        break

HAS_TTF = _TTF_BOLD is not None and "dejavu" in _TTF_BOLD.lower()
ARROW_L = "\u2190" if HAS_TTF else "<"
ARROW_R = "\u2192" if HAS_TTF else "->"
INTEG   = "\u222b" if HAS_TTF else "Int"
_FONT_CACHE = {}


def get_font(size, bold=True):
    key = (size, bold)
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]
    f = None
    path = _TTF_BOLD if bold else _TTF_REG
    if path:
        try:
            f = ImageFont.truetype(path, size)
        except Exception:
            f = None
    if f is None:
        try:
            f = ImageFont.load_default(size)
        except Exception:
            f = ImageFont.load_default()
    _FONT_CACHE[key] = f
    return f


def tw(draw, s, font):
    try:
        return draw.textlength(s, font=font)
    except Exception:
        return len(s) * 6


def fit_font(draw, s, max_w, sizes, bold=True):
    for sz in sizes:
        f = get_font(sz, bold)
        if tw(draw, s, f) <= max_w:
            return f
    return get_font(sizes[-1], bold)


def fit_tail(draw, s, max_w, font):
    """Keep the END of a string that is too long (like a real calculator)."""
    while len(s) > 1 and tw(draw, s, font) > max_w:
        s = s[1:]
    return s


def wrap_text(draw, s, font, max_w, max_lines):
    lines, cur = [], ""
    for ch in s:
        if tw(draw, cur + ch, font) > max_w and cur:
            lines.append(cur)
            cur = ch
        else:
            cur += ch
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1][:-2] + ".."
    return lines


def draw_text_c(draw, cx, cy, s, font, fill):
    bb = draw.textbbox((0, 0), s, font=font)
    w = bb[2] - bb[0]
    h = bb[3] - bb[1]
    draw.text((cx - w / 2.0 - bb[0], cy - h / 2.0 - bb[1]), s, font=font, fill=fill)


def draw_text_r(draw, x_right, y, s, font, fill):
    draw.text((x_right - tw(draw, s, font), y), s, font=font, fill=fill)


def rbox(draw, box, fill, outline=None, r=6):
    if hasattr(draw, "rounded_rectangle"):
        draw.rounded_rectangle(box, radius=r, fill=fill, outline=outline)
    else:
        draw.rectangle(box, fill=fill, outline=outline)


def pretty(s):
    """Display-only prettifying: x**2 -> x^2 -> x2 (superscript)."""
    s = s.replace("**", "^")
    if HAS_TTF:
        s = re.sub(r"\^2(?!\d)", "\u00b2", s)
        s = re.sub(r"\^3(?!\d)", "\u00b3", s)
    return s


def pretty_entry(s):
    s = pretty(s)
    if HAS_TTF:
        s = s.replace("*", "\u00d7")
    return s


# ------------------------------------------------
#  LAYOUT CONSTANTS
# ------------------------------------------------
HEADER_H  = 20
DISPLAY_H = 48
BTN_TOP   = HEADER_H + DISPLAY_H      # 68
BTN_AREA  = SH - BTN_TOP
GAP       = 3

HOME_BOX = (0, 0, 92, HEADER_H + 8, "NAV_HOME")   # "< HOME" hit area


def make_buttons(layout, rows=5, cols=4):
    btn_w = (SW - GAP * (cols + 1)) // cols
    btn_h = (BTN_AREA - GAP * (rows + 1)) // rows
    result = []
    for (label, action, color, row, col, colspan) in layout:
        x1 = GAP + col * (btn_w + GAP)
        y1 = BTN_TOP + GAP + row * (btn_h + GAP)
        x2 = x1 + btn_w * colspan + GAP * (colspan - 1)
        y2 = y1 + btn_h
        result.append({"label": label, "action": action, "color": color,
                       "x1": x1, "y1": y1, "x2": x2, "y2": y2})
    return result


def make_numpad(prefix, top, bottom):
    """4x5 keypad: row0 = top, rows1-3 = digits/operators, row4 = bottom."""
    mid = [["7", "8", "9", "/"], ["4", "5", "6", "*"], ["1", "2", "3", "-"]]
    layout = []
    for c, (lbl, act, col) in enumerate(top):
        layout.append((lbl, act, col, 0, c, 1))
    for r, row in enumerate(mid, 1):
        for c, k in enumerate(row):
            layout.append((k, prefix + k, C_NUM if k.isdigit() else C_OP, r, c, 1))
    for c, (lbl, act, col) in enumerate(bottom):
        layout.append((lbl, act, col, 4, c, 1))
    return make_buttons(layout)


# ------------------------------------------------
#  KEYPADS
# ------------------------------------------------
_CALC_BOTTOM = [("0", "0", C_NUM), (".", ".", C_NUM), ("=", "=", C_EQUAL), ("+", "+", C_OP)]

CALC_BTNS = make_numpad("", [("AC", "AC", C_CLEAR), ("MISC", "M_CALC", C_FUNC),
                             ("(", "(", C_OP), (")", ")", C_OP)], _CALC_BOTTOM)
SCI_BTNS  = make_numpad("", [("AC", "AC", C_CLEAR), ("MATH", "M_SCI", C_FUNC),
                             ("(", "(", C_OP), (")", ")", C_OP)], _CALC_BOTTOM)
TRIG_BTNS = make_numpad("", [("AC", "AC", C_CLEAR), ("TRIG", "M_TRIG", C_TRIG),
                             ("(", "(", C_OP), (")", ")", C_OP)], _CALC_BOTTOM)

GRAPH_BTNS = make_numpad("GT:", [("MATH", "M_G_MATH", C_FUNC), ("VAR", "M_G_VAR", C_VAR),
                                 ("RNG", "M_G_RNG", C_RANGE), ("PLOT", "PLOT", C_GRAPH)],
                         [("0", "GT:0", C_NUM), (".", "GT:.", C_NUM),
                          ("CLR", "GCLR", C_CLEAR), ("+", "GT:+", C_OP)])

TD_BTNS = make_numpad("T3:", [("PRE", "M_3D_PRE", C_3DB), ("MATH", "M_3D_MATH", C_TRIG),
                              ("VIEW", "M_3D_VIEW", C_ROT), ("PLOT", "TD:PLOT", C_GRAPH)],
                      [("0", "T3:0", C_NUM), (".", "T3:.", C_NUM),
                       ("CLR", "T3CLR", C_CLEAR), ("+", "T3:+", C_OP)])

# CAS keypad: 6 rows x 5 columns. All seven operations are one tap away.
_CAS_ROWS = [
    ("d/dx", "DERIV", C_CAS, 0, 0), ("Int", "INTEG", C_CAS, 0, 1),
    ("Simp", "SIMPLIFY", C_CAS, 0, 2), ("Expd", "EXPAND", C_CAS, 0, 3),
    ("AC", "AC", C_CLEAR, 0, 4),
    ("Factor", "FACTOR", C_CAS, 1, 0), ("Limit", "LIMIT", C_CAS, 1, 1),
    ("Solve", "SOLVE", C_CAS, 1, 2), ("MORE", "M_CAS", C_FUNC, 1, 3),
    ("DEL", "DEL", C_CLEAR, 1, 4),
    ("7", "CT:7", C_NUM, 2, 0), ("8", "CT:8", C_NUM, 2, 1), ("9", "CT:9", C_NUM, 2, 2),
    ("/", "CT:/", C_OP, 2, 3), ("(", "CT:(", C_OP, 2, 4),
    ("4", "CT:4", C_NUM, 3, 0), ("5", "CT:5", C_NUM, 3, 1), ("6", "CT:6", C_NUM, 3, 2),
    ("*", "CT:*", C_OP, 3, 3), (")", "CT:)", C_OP, 3, 4),
    ("1", "CT:1", C_NUM, 4, 0), ("2", "CT:2", C_NUM, 4, 1), ("3", "CT:3", C_NUM, 4, 2),
    ("-", "CT:-", C_OP, 4, 3), ("x", "CASX", C_VAR, 4, 4),
    ("0", "CT:0", C_NUM, 5, 0), (".", "CT:.", C_NUM, 5, 1), ("^", "CT:^", C_OP, 5, 2),
    ("+", "CT:+", C_OP, 5, 3), ("x\u00b2" if HAS_TTF else "x^2", "CASX2", C_VAR, 5, 4),
]
CAS_BTNS = make_buttons([(l, a, c, r, col, 1) for (l, a, c, r, col) in _CAS_ROWS],
                        rows=6, cols=5)

CAS_OPS = ("DERIV", "INTEG", "SIMPLIFY", "EXPAND", "FACTOR", "LIMIT", "SOLVE")

CALC_SCREENS = ("CALC", "SCI", "TRIG")

PANELS = {
    "CALC":  (CALC_BTNS,  "Calculator"),
    "SCI":   (SCI_BTNS,   "Scientific"),
    "TRIG":  (TRIG_BTNS,  "Trigonometry"),
    "CAS":   (CAS_BTNS,   "CAS"),
    "GRAPH": (GRAPH_BTNS, "Graph"),
    "3D":    (TD_BTNS,    "3D Graph"),
}

# every keypad screen: the HOME button plus its keys
KEYPAD_BOXES = {}
for _name, (_btns, _t) in PANELS.items():
    KEYPAD_BOXES[_name] = [HOME_BOX] + [
        (b["x1"], b["y1"], b["x2"], b["y2"], b["action"]) for b in _btns]

# ------------------------------------------------
#  SUBMENUS
# ------------------------------------------------
TD_PRESETS = {
    "sincos": "sin(x)*cos(y)",
    "parab":  "x**2+y**2",
    "ripple": "sin(sqrt(x**2+y**2))",
    "saddle": "x**2-y**2",
    "cone":   "sqrt(x**2+y**2)",
    "wave":   "sin(x)+cos(y)",
    "twist":  "sin(x*y)",
    "bowl":   "-(x**2+y**2)",
    "gauss":  "exp(-(x**2+y**2))",
    "torus":  "sin(x*y)+cos(x+y)",
}

active_submenu   = None
submenu_hitboxes = []

SUBMENUS = {
    "M_CALC": [
        ("+/-", "NEG"), ("%", "PCT"), ("pi", "pi"), ("e", "e"), ("DEL", "DEL")
    ],
    "M_TRIG": [
        ("sin", "sin("), ("cos", "cos("), ("tan", "tan("),
        ("asin", "asin("), ("acos", "acos("), ("atan", "atan("),
        ("sinh", "sinh("), ("cosh", "cosh("), ("tanh", "tanh("),
        ("pi", "pi"), ("DEG/RAD", "TOGGLE_ANG"), ("DEL", "DEL")
    ],
    "M_SCI": [
        ("x^2", "**2"), ("x^y", "**"), ("sqrt", "sqrt("),
        ("log", "log10("), ("ln", "log("), ("exp", "exp("),
        ("abs", "abs("), ("e", "e"), ("n!", "FACT"),
        ("DEG/RAD", "TOGGLE_ANG"), ("DEL", "DEL")
    ],
    # CAS MORE: functions, variables and "use result as expression"
    "M_CAS": [
        ("sin", "CT:sin("), ("cos", "CT:cos("), ("tan", "CT:tan("),
        ("ln", "CT:log("), ("sqrt", "CT:sqrt("), ("exp", "CT:exp("),
        ("pi", "CT:pi"), ("e", "CT:e"), ("->Expr", "TOEXPR"),
        ("t", "CASVAR:t"), ("a", "CASVAR:a"), ("k", "CASVAR:k"), ("n", "CASVAR:n")
    ],
    "M_G_MATH": [
        ("sin", "GT:sin("), ("cos", "GT:cos("), ("tan", "GT:tan("),
        ("log", "GT:log10("), ("ln", "GT:log("), ("sqrt", "GT:sqrt("),
        ("x^2", "GT:x**2"), ("(", "GT:("), (")", "GT:)"), ("^", "GT:**")
    ],
    "M_G_VAR": [("x", "GT:x")],
    "M_G_RNG": [("x>0", "GR:pos"), ("full", "GR:full"), ("wide", "GR:wide")],
    "M_3D_PRE": [
        ("sincos", "TD:sincos"), ("ripple", "TD:ripple"),
        ("gauss", "TD:gauss"), ("torus", "TD:torus"),
        ("saddle", "TD:saddle"), ("cone", "TD:cone")
    ],
    "M_3D_MATH": [
        ("sin(", "T3:sin("), ("cos(", "T3:cos("),
        ("sqrt(", "T3:sqrt("), ("exp(", "T3:exp("),
        ("^", "T3:**"), ("x", "T3:x"), ("y", "T3:y"),
        ("(", "T3:("), (")", "T3:)")
    ],
    "M_3D_VIEW": [
        ("RotL", "TD:RL"), ("RotR", "TD:RR"),
        ("TiltU", "TD:TU"), ("TiltD", "TD:TD_"),
        ("FINE", "TD:FINE"), ("COARSE", "TD:COARSE"),
        ("RESET", "TD:RESET")
    ],
}

# ------------------------------------------------
#  HOME + SETTINGS LAYOUT
# ------------------------------------------------
HOME_TILES = [
    ("Calculator",   "CALC",  (20, 55, 110),  0, 0),
    ("Scientific",   "SCI",   (20, 85, 55),   0, 1),
    ("Trigonometry", "TRIG",  (80, 30, 100),  1, 0),
    ("CAS",          "CAS",   (110, 60, 10),  1, 1),
    ("Graph",        "GRAPH", (0, 105, 80),   2, 0),
    ("3D Graph",     "3D",    (30, 70, 130),  2, 1),
]
_HT_MARGIN, _HT_GAP, _HT_TOP, _HT_H = 8, 8, 48, 36
_HT_W = (SW - 2 * _HT_MARGIN - _HT_GAP) // 2


def _tile_box(row, col):
    x1 = _HT_MARGIN + col * (_HT_W + _HT_GAP)
    y1 = _HT_TOP + row * (_HT_H + _HT_GAP)
    return (x1, y1, x1 + _HT_W, y1 + _HT_H)


_SET_W = 150
_SET_BOX = ((SW - _SET_W) // 2, _HT_TOP + 3 * (_HT_H + _HT_GAP),
            (SW + _SET_W) // 2, _HT_TOP + 3 * (_HT_H + _HT_GAP) + _HT_H)

HOME_BOXES = [_tile_box(r, c) + ("NAV:" + act,) for (_l, act, _col, r, c) in HOME_TILES]
HOME_BOXES.append(_SET_BOX + ("NAV:SETTINGS",))

SET_ROW_Y0, SET_ROW_H, SET_ROW_GAP = 26, 42, 6
SET_HOME_BOX = ((SW - 150) // 2, 196, (SW + 150) // 2, 230)
SETTINGS_BOXES = []
for _i, _act in enumerate(("TOG_WIFI", "TOG_BT", "TOG_PWR")):
    _y1 = SET_ROW_Y0 + _i * (SET_ROW_H + SET_ROW_GAP)
    SETTINGS_BOXES.append((8, _y1, SW - 8, _y1 + SET_ROW_H, _act))
SETTINGS_BOXES.append(SET_HOME_BOX + ("NAV_HOME",))
SETTINGS_BOXES.append(HOME_BOX)

# ------------------------------------------------
#  STATE
# ------------------------------------------------
screen        = "HOME"
showing_graph = False
showing_3d    = False
notice        = ""          # short error line for Graph / 3D

# Calculator / Scientific / Trig (shared)
expression    = ""
result_str    = "0"
just_result   = False
angle_deg     = True

# CAS
cas_expr      = ""
cas_var       = "x"
cas_show      = ""          # text shown as the result
cas_value     = ""          # plain expression usable by "->Expr"

# Graph
graph_expr    = "x"
graph_xmode   = "full"

# 3D
td_func_name  = "sincos"
td_func_expr  = TD_PRESETS["sincos"]
td_user_expr  = ""
td_azimuth    = 45
td_elevation  = 30
td_grid_res   = 20

# Settings
wifi_on       = None        # True / False / None (unknown)
bt_on         = None
power_save    = False
settings_msg  = ""

# Battery: intentionally NOT implemented (no fake readings).
# When the ADS1115 is installed, implement read_battery_percent() and draw it
# in draw_header().
BATTERY_AVAILABLE = False


def read_battery_percent():
    return None


# ------------------------------------------------
#  VALIDATION / COLOR HELPERS
# ------------------------------------------------
def validate_expr(expr):
    if not expr:
        return False, "Empty expression"
    try:
        compile(expr, "<string>", "eval")
    except SyntaxError as e:
        return False, "Syntax error: " + str(e.msg)[:14]
    return True, "OK"


def z_to_color(t):
    t = max(0.0, min(1.0, float(t)))
    if t < 0.25:
        return (0, int(t * 4 * 255), 255)
    elif t < 0.5:
        return (0, 255, int((0.5 - t) * 4 * 255))
    elif t < 0.75:
        return (int((t - 0.5) * 4 * 255), 255, 0)
    else:
        return (255, int((1.0 - t) * 4 * 255), 0)


# ------------------------------------------------
#  SYSTEM CONTROL  (Wi-Fi / Bluetooth / Power saving)
# ------------------------------------------------
def run_cmd(args, input_text=None, timeout=6, need_root=True):
    cmd = list(args)
    if need_root and hasattr(os, "geteuid") and os.geteuid() != 0:
        cmd = ["sudo", "-n"] + cmd
    try:
        r = subprocess.run(cmd, input=input_text, capture_output=True,
                           text=True, timeout=timeout)
        return r.returncode == 0, (r.stdout + r.stderr).strip()
    except Exception as ex:
        return False, str(ex)


def rfkill_state(kind):
    """True = radio on, False = soft-blocked (off), None = unknown."""
    try:
        r = subprocess.run(["rfkill", "list", kind], capture_output=True,
                           text=True, timeout=4)
        softs = re.findall(r"Soft blocked:\s*(yes|no)", r.stdout)
    except Exception:
        return None
    if not softs:
        return None
    return not all(s == "yes" for s in softs)


def set_radio(kind, on):
    ok, msg = run_cmd(["rfkill", "unblock" if on else "block", kind])
    return ok, msg


def refresh_radio_states():
    global wifi_on, bt_on
    wifi_on = rfkill_state("wifi")
    bt_on   = rfkill_state("bluetooth")


def sysfs_write(path, value):
    try:
        with open(path, "w") as f:
            f.write(value)
        return True
    except Exception:
        ok, _ = run_cmd(["tee", path], input_text=value)
        return ok


def _read_text(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except Exception:
        return None


# Power saving only touches things a calculator does not need.
# It never stops any system service, and everything is restored when turned off.
PS_HDMI_OFF = True          # set False if you use an HDMI monitor while testing
_ps_saved   = {}


def apply_power_save(on):
    """Returns (success, list_of_things_changed)."""
    done = []
    if on:
        saved_gov = {}
        for p in glob.glob("/sys/devices/system/cpu/cpu[0-9]*/cpufreq/scaling_governor"):
            cur = _read_text(p)
            if cur is None:
                continue
            if cur == "powersave" or sysfs_write(p, "powersave"):
                saved_gov[p] = cur
        if saved_gov:
            _ps_saved["gov"] = saved_gov
            done.append("CPU")

        saved_led = {}
        for name in ("ACT", "led0", "PWR", "led1"):
            base = "/sys/class/leds/" + name + "/"
            trig = _read_text(base + "trigger")
            bri  = _read_text(base + "brightness")
            if trig is None or bri is None:
                continue
            m = re.search(r"\[([^\]]+)\]", trig)
            prev_trig = m.group(1) if m else "none"
            if sysfs_write(base + "trigger", "none") and sysfs_write(base + "brightness", "0"):
                saved_led[base] = (prev_trig, bri)
        if saved_led:
            _ps_saved["led"] = saved_led
            done.append("LEDs")

        if PS_HDMI_OFF:
            ok, out = run_cmd(["vcgencmd", "display_power", "0"])
            if ok and "display_power=0" in out:
                _ps_saved["hdmi"] = True
                done.append("HDMI")
        return bool(done), done

    # ---- restore ----
    for p, cur in _ps_saved.pop("gov", {}).items():
        sysfs_write(p, cur)
        done.append("CPU")
    for base, (trig, bri) in _ps_saved.pop("led", {}).items():
        sysfs_write(base + "trigger", trig)
        if trig == "none":
            sysfs_write(base + "brightness", bri)
    if _ps_saved.pop("hdmi", False):
        run_cmd(["vcgencmd", "display_power", "1"])
    return True, done


def poll_delay():
    return 0.06 if power_save else 0.02


def handle_settings(action):
    global wifi_on, bt_on, power_save, settings_msg
    if action in ("TOG_WIFI", "TOG_BT"):
        kind, label = ("wifi", "Wi-Fi") if action == "TOG_WIFI" else ("bluetooth", "Bluetooth")
        cur = rfkill_state(kind)
        if cur is None:
            settings_msg = label + ": control unavailable (rfkill missing)"
        else:
            ok, msg = set_radio(kind, not cur)
            new = rfkill_state(kind)                  # show the REAL state
            if action == "TOG_WIFI":
                wifi_on = new
            else:
                bt_on = new
            if ok and new == (not cur):
                settings_msg = label + (" turned ON" if new else " turned OFF")
            else:
                settings_msg = label + ": needs root (run with sudo)"
        return

    if action == "TOG_PWR":
        ok, done = apply_power_save(not power_save)
        if power_save:                                 # turning OFF
            power_save = False
            settings_msg = "Power saving OFF - normal mode"
        elif ok:
            power_save = True
            settings_msg = "Power saving ON: " + ", ".join(done)
        else:
            settings_msg = "Power saving: needs root (run with sudo)"


# ------------------------------------------------
#  DRAWING - COMMON
# ------------------------------------------------
def draw_header(draw, title):
    draw.rectangle((0, 0, SW, HEADER_H), fill=C_HEADER)
    draw.line((0, HEADER_H, SW, HEADER_H), fill=C_OUTLINE)
    if title != "HOME":
        rbox(draw, (3, 2, 70, HEADER_H - 2), C_HOMEBTN, C_ACCENT, 4)
        draw_text_c(draw, 36, HEADER_H // 2, ARROW_L + " HOME", get_font(11), C_TEXT)
    draw_text_c(draw, SW // 2 + 30, HEADER_H // 2, title, get_font(13), C_ACCENT)
    if BATTERY_AVAILABLE:
        pct = read_battery_percent()
        if pct is not None:
            draw_text_r(draw, SW - 4, 3, str(pct) + "%", get_font(11), C_TEXT)


def draw_keypad(draw, buttons, highlight=None):
    for b in buttons:
        is_hi   = (highlight == b["action"])
        fill    = C_HI if is_hi else b["color"]
        outline = (255, 255, 255) if is_hi else C_OUTLINE
        draw.rectangle((b["x1"], b["y1"], b["x2"], b["y2"]), fill=fill, outline=outline)
        bw = b["x2"] - b["x1"]
        f  = fit_font(draw, b["label"], bw - 4, (13, 11, 9))
        draw_text_c(draw, (b["x1"] + b["x2"]) / 2.0, (b["y1"] + b["y2"]) / 2.0,
                    b["label"], f, C_TEXT)


def draw_submenu(draw, menu_key):
    global submenu_hitboxes
    submenu_hitboxes = []
    if menu_key not in SUBMENUS:
        return
    items = SUBMENUS[menu_key]
    cols = 3
    rows = math.ceil(len(items) / cols)

    margin_x = 15
    margin_y = 30
    w = SW - 2 * margin_x
    h = min(SH - 2 * margin_y, 40 + rows * 40)

    draw.rectangle((margin_x + 4, margin_y + 4, margin_x + w + 4, margin_y + h + 4), fill=(0, 0, 0))
    draw.rectangle((margin_x, margin_y, margin_x + w, margin_y + h),
                   fill=(20, 25, 40), outline=C_ACCENT, width=2)
    draw.text((margin_x + 8, margin_y + 6), "Select option (tap outside to close)",
              font=get_font(10, False), fill=C_ACCENT)

    start_y = margin_y + 25
    avail_h = h - 30
    btn_w = (w - (cols + 1) * GAP) // cols
    btn_h = (avail_h - (rows + 1) * GAP) // rows

    for i, (lbl, act) in enumerate(items):
        r = i // cols
        c = i % cols
        x1 = margin_x + GAP + c * (btn_w + GAP)
        y1 = start_y + GAP + r * (btn_h + GAP)
        x2 = x1 + btn_w
        y2 = y1 + btn_h
        draw.rectangle((x1, y1, x2, y2), fill=C_OP, outline=C_TEXT)
        f = fit_font(draw, lbl, btn_w - 4, (12, 10, 9))
        draw_text_c(draw, (x1 + x2) / 2.0, (y1 + y2) / 2.0, lbl, f, C_TEXT)
        submenu_hitboxes.append({"action": act, "x1": x1, "y1": y1, "x2": x2, "y2": y2})


# ------------------------------------------------
#  DRAWING - DISPLAY AREAS
# ------------------------------------------------
def _display_bg(draw):
    y0 = HEADER_H
    draw.rectangle((0, y0 + 1, SW, y0 + DISPLAY_H), fill=C_DISP)
    draw.rectangle((0, y0 + DISPLAY_H - 2, SW, y0 + DISPLAY_H), fill=C_ACCENT)


def draw_display_calc(draw):
    _display_bg(draw)
    y0 = HEADER_H
    expr = expression or "0"
    f = fit_font(draw, expr, SW - 12, (14, 12))
    expr = fit_tail(draw, expr, SW - 12, f)
    draw.text((6, y0 + 4), expr, font=f, fill=C_EXPR)

    res = result_str[:24]
    rf = fit_font(draw, res, SW - 14, (20, 16, 13))
    draw_text_r(draw, SW - 7, y0 + 21, res, rf, C_RES)
    draw.text((6, y0 + 30), "DEG" if angle_deg else "RAD", font=get_font(10), fill=C_TEXDIM)


def draw_display_cas(draw):
    _display_bg(draw)
    y0 = HEADER_H
    draw_text_r(draw, SW - 6, y0 + 4, "d/d" + cas_var, get_font(10), (180, 120, 255))

    if cas_expr:
        e = pretty_entry(cas_expr)
        f = fit_font(draw, e, SW - 56, (15, 13, 11))
        e = fit_tail(draw, e, SW - 56, f)
        draw.text((6, y0 + 3), e, font=f, fill=C_EXPR)
    else:
        draw.text((6, y0 + 5), "Type e.g.  3x^2  then tap d/dx",
                  font=get_font(11, False), fill=C_TEXDIM)

    if cas_show:
        txt = pretty(cas_show)
        for sz, lines_max in ((15, 1), (13, 1), (11, 2)):
            f = get_font(sz)
            lines = wrap_text(draw, txt, f, SW - 12, lines_max)
            if len(lines) <= lines_max and (lines_max == 2 or tw(draw, txt, f) <= SW - 12):
                break
        ly = y0 + 24 if len(lines) == 1 else y0 + 20
        for ln in lines:
            draw.text((6, ly), ln, font=f, fill=C_RES)
            ly += sz + 2


def draw_display_graph(draw):
    _display_bg(draw)
    y0 = HEADER_H
    rng = "x>0 (0.001 to 10)" if graph_xmode == "pos" else \
          "x: -50 to 50"      if graph_xmode == "wide" else "x: -10 to 10"
    draw.text((6, y0 + 3), ("f(x)= " + graph_expr)[-34:], font=get_font(13), fill=C_EXPR)
    draw.text((6, y0 + 22), rng, font=get_font(11, False), fill=C_TEXDIM)
    if notice:
        draw.text((6, y0 + 33), notice[:44], font=get_font(10), fill=C_WARN)
    else:
        draw.text((6, y0 + 33), "RNG sets the window, PLOT draws",
                  font=get_font(10, False), fill=(80, 90, 130))


def draw_display_3d(draw):
    _display_bg(draw)
    y0 = HEADER_H
    active = td_user_expr if td_user_expr else td_func_expr
    draw.text((6, y0 + 3), "f(x,y)= " + active[-28:], font=get_font(12), fill=C_EXPR)
    draw.text((6, y0 + 20), "Az:" + str(td_azimuth) + "  El:" + str(td_elevation),
              font=get_font(11, False), fill=C_TEXDIM)
    res_lbl = "FINE(25)" if td_grid_res >= 25 else ("MED(20)" if td_grid_res >= 20 else "COARSE(15)")
    draw_text_r(draw, SW - 6, y0 + 20, res_lbl, get_font(11, False), C_TEXDIM)
    if notice:
        draw.text((6, y0 + 33), notice[:44], font=get_font(10), fill=C_WARN)
    elif td_user_expr:
        draw.text((6, y0 + 33), "USER> " + td_user_expr[-34:], font=get_font(10), fill=(0, 220, 140))


# ------------------------------------------------
#  DRAWING - SCREENS
# ------------------------------------------------
def draw_home():
    image = Image.new("RGB", device.size, C_BG)
    draw = ImageDraw.Draw(image)

    draw_text_c(draw, SW // 2, 14, "KUSHBOTICS", get_font(20), C_BRAND)
    draw_text_c(draw, SW // 2, 34, "CALCULATOR", get_font(12), C_TEXT)
    draw.line((12, 43, SW - 12, 43), fill=C_OUTLINE)

    for (label, act, col, r, c) in HOME_TILES:
        x1, y1, x2, y2 = _tile_box(r, c)
        rbox(draw, (x1, y1, x2, y2), col, C_ACCENT, 7)
        f = fit_font(draw, label, _HT_W - 8, (15, 13, 11))
        draw_text_c(draw, (x1 + x2) / 2.0, (y1 + y2) / 2.0, label, f, C_TEXT)

    x1, y1, x2, y2 = _SET_BOX
    rbox(draw, (x1, y1, x2, y2), (45, 48, 70), C_TEXDIM, 7)
    draw_text_c(draw, (x1 + x2) / 2.0, (y1 + y2) / 2.0, "Settings", get_font(15), C_TEXT)

    def st(v):
        return "n/a" if v is None else ("ON" if v else "OFF")
    foot = "Wi-Fi " + st(wifi_on) + "   BT " + st(bt_on) + "   Eco " + ("ON" if power_save else "OFF")
    draw_text_c(draw, SW // 2, SH - 9, foot, get_font(10, False), C_TEXDIM)
    device.display(image)


def draw_settings():
    image = Image.new("RGB", device.size, C_BG)
    draw = ImageDraw.Draw(image)
    draw_header(draw, "SETTINGS")

    rows = [
        ("Wi-Fi",        "Turn OFF for offline use",       wifi_on),
        ("Bluetooth",    "Turn OFF when not needed",       bt_on),
        ("Power Saving", "Slower CPU, LEDs & HDMI off",    power_save),
    ]
    for i, (label, sub, state) in enumerate(rows):
        y1 = SET_ROW_Y0 + i * (SET_ROW_H + SET_ROW_GAP)
        y2 = y1 + SET_ROW_H
        rbox(draw, (8, y1, SW - 8, y2), (22, 26, 50), C_OUTLINE, 6)
        draw.text((18, y1 + 6), label, font=get_font(15), fill=C_TEXT)
        draw.text((18, y1 + 26), sub, font=get_font(10, False), fill=C_TEXDIM)
        if state is None:
            col, txt = C_NA, "N/A"
        elif state:
            col, txt = C_ON, "ON"
        else:
            col, txt = C_OFF, "OFF"
        rbox(draw, (SW - 90, y1 + 7, SW - 18, y2 - 7), col, C_TEXT, 6)
        draw_text_c(draw, SW - 54, (y1 + y2) / 2.0, txt, get_font(14), C_TEXT)

    if settings_msg:
        f = get_font(11, False)
        for j, ln in enumerate(wrap_text(draw, settings_msg, f, SW - 20, 2)):
            draw_text_c(draw, SW // 2, 176 + j * 13, ln, f, C_WARN if "needs" in settings_msg
                        or "unavailable" in settings_msg else C_RES)

    x1, y1, x2, y2 = SET_HOME_BOX
    rbox(draw, (x1, y1, x2, y2), C_HOMEBTN, C_ACCENT, 7)
    draw_text_c(draw, (x1 + x2) / 2.0, (y1 + y2) / 2.0, "HOME", get_font(15), C_TEXT)
    device.display(image)


def draw_ui(highlight=None):
    global showing_graph, showing_3d
    showing_graph = False
    showing_3d    = False

    if screen == "HOME":
        draw_home()
        return
    if screen == "SETTINGS":
        draw_settings()
        return

    buttons, title = PANELS[screen]
    image = Image.new("RGB", device.size, C_BG)
    draw = ImageDraw.Draw(image)
    draw_header(draw, title)
    if screen in CALC_SCREENS:
        draw_display_calc(draw)
    elif screen == "CAS":
        draw_display_cas(draw)
    elif screen == "GRAPH":
        draw_display_graph(draw)
    else:
        draw_display_3d(draw)
    draw_keypad(draw, buttons, highlight)
    if active_submenu:
        draw_submenu(draw, active_submenu)
    device.display(image)


# ------------------------------------------------
#  2D GRAPH
# ------------------------------------------------
def draw_graph():
    global showing_graph, notice
    if not HAS_NUMPY:
        notice = "numpy not installed"
        return
    try:
        expr = graph_expr.strip()
        ok, msg = validate_expr(expr)
        if not ok:
            notice = msg
            return

        if graph_xmode == "pos":
            x_start, x_end = 0.001, 10.0
        elif graph_xmode == "wide":
            x_start, x_end = -50.0, 50.0
        else:
            x_start, x_end = -10.0, 10.0

        x_vals = np.linspace(x_start, x_end, SW)

        with np.errstate(divide='ignore', invalid='ignore'):
            safe = {
                "x": x_vals, "pi": np.pi, "e": np.e,
                "sin":  np.sin,    "cos":  np.cos,    "tan":  np.tan,
                "asin": np.arcsin, "acos": np.arccos, "atan": np.arctan,
                "sinh": np.sinh,   "cosh": np.cosh,   "tanh": np.tanh,
                "log":  np.log,    "log10": np.log10, "sqrt": np.sqrt,
                "abs":  np.abs,    "exp":  np.exp,
            }
            y_vals = eval(expr, {"__builtins__": {}}, safe)

        # constants such as "5" give a scalar - expand to one value per pixel
        y_vals = np.array(np.broadcast_to(np.array(y_vals, dtype=float), x_vals.shape))
        y_vals[~np.isfinite(y_vals)] = np.nan

        if np.all(np.isnan(y_vals)):
            notice = "No real values in range"
            return
        y_min = np.nanmin(y_vals)
        y_max = np.nanmax(y_vals)
        if y_min == y_max:
            y_min -= 1.0
            y_max += 1.0

        image = Image.new("RGB", device.size, (8, 8, 18))
        draw  = ImageDraw.Draw(image)
        draw.rectangle((0, 0, SW - 1, SH - 1), outline=(40, 40, 70))

        if y_min <= 0 <= y_max:
            zero_y = SH - int((0 - y_min) / (y_max - y_min) * SH)
            if 0 <= zero_y < SH:
                draw.line((0, zero_y, SW, zero_y), fill=(60, 60, 100))
        if x_start <= 0 <= x_end:
            zero_x = int((0 - x_start) / (x_end - x_start) * SW)
            if 0 <= zero_x < SW:
                draw.line((zero_x, 0, zero_x, SH), fill=(60, 60, 100))

        prev = None
        for i in range(SW):
            y = y_vals[i]
            if np.isnan(y):
                prev = None
                continue
            py = SH - int((y - y_min) / (y_max - y_min) * SH)
            py = max(0, min(SH - 1, py))
            ratio = i / SW
            c = (0, int(220 - 60 * ratio), int(255 - 95 * ratio))
            if prev is not None and abs(py - prev[1]) < SH // 2:
                draw.line((prev[0], prev[1], i, py), fill=c, width=2)
            prev = (i, py)

        draw.text((4, 2),  "f(x)=" + expr[:30], font=get_font(11), fill=(120, 180, 255))
        draw.text((4, 16), "y:" + str(round(float(y_min), 3)) + " to " +
                  str(round(float(y_max), 3)), font=get_font(10, False), fill=(80, 120, 180))
        x_lbl = "x:" + str(round(x_start, 3)) + " to " + str(int(x_end))
        draw_text_r(draw, SW - 4, SH - 14, x_lbl, get_font(10, False), (80, 120, 180))
        draw.text((4, SH - 14), "Tap to return", font=get_font(10, False), fill=(80, 100, 140))

        device.display(image)
        showing_graph = True

    except Exception as ex:
        notice = "Error: " + str(ex)[:34]


# ------------------------------------------------
#  3D SURFACE
# ------------------------------------------------
def render_3d_surface():
    global showing_3d, notice
    if not HAS_NUMPY:
        notice = "numpy not installed"
        return
    try:
        if td_user_expr.strip():
            plot_expr = td_user_expr.strip()
            plot_name = "USER"
        else:
            plot_expr = td_func_expr
            plot_name = td_func_name

        ok, msg = validate_expr(plot_expr)
        if not ok:
            notice = msg
            return
        if not ("x" in plot_expr or "y" in plot_expr):
            notice = "Expression needs x or y"
            return

        n    = td_grid_res
        lim  = 3.0
        x1d  = np.linspace(-lim, lim, n)
        y1d  = np.linspace(-lim, lim, n)
        X, Y = np.meshgrid(x1d, y1d)

        with np.errstate(divide='ignore', invalid='ignore'):
            safe_3d = {
                "x": X, "y": Y,
                "sin":  np.sin,   "cos":  np.cos,   "tan":  np.tan,
                "asin": np.arcsin, "acos": np.arccos, "atan": np.arctan,
                "sinh": np.sinh,  "cosh": np.cosh,  "tanh": np.tanh,
                "sqrt": np.sqrt,  "abs":  np.abs,   "exp":  np.exp,
                "log":  np.log,   "log10": np.log10,
                "pi":   np.pi,    "e":    np.e,
            }
            Z = eval(plot_expr, {"__builtins__": {}}, safe_3d)

        Z = np.array(np.broadcast_to(np.array(Z, dtype=float), X.shape))
        Z[~np.isfinite(Z)] = 0.0

        z_min = float(Z.min())
        z_max = float(Z.max())
        if z_min == z_max:
            z_max = z_min + 1.0
        Z_norm = (Z - z_min) / (z_max - z_min)

        Xn = X / lim
        Yn = Y / lim
        Zn = Z_norm * 1.4 - 0.7

        az     = math.radians(td_azimuth)
        el     = math.radians(td_elevation)
        cos_az = math.cos(az)
        sin_az = math.sin(az)
        cos_el = math.cos(el)
        sin_el = math.sin(el)

        Xr  = Xn * cos_az - Yn * sin_az
        Yr  = Xn * sin_az + Yn * cos_az
        Yr2 = Yr * cos_el - Zn * sin_el

        scale = int(min(SW, SH) * 0.40)
        cx    = SW // 2
        cy    = SH // 2

        SX = np.clip((cx + Xr  * scale).astype(int), 0, SW - 1)
        SY = np.clip((cy - Yr2 * scale).astype(int), 0, SH - 1)

        image = Image.new("RGB", device.size, (5, 5, 15))
        draw  = ImageDraw.Draw(image)

        for i in range(n):
            for j in range(n):
                c = z_to_color(Z_norm[i, j])
                if j < n - 1:
                    draw.line([(int(SX[i, j]),     int(SY[i, j])),
                               (int(SX[i, j + 1]), int(SY[i, j + 1]))], fill=c, width=1)
                if i < n - 1:
                    draw.line([(int(SX[i, j]),     int(SY[i, j])),
                               (int(SX[i + 1, j]), int(SY[i + 1, j]))], fill=c, width=1)

        for py in range(SH):
            col = z_to_color(1.0 - py / SH)
            for px in range(SW - 5, SW - 2):
                draw.point((px, py), fill=col)

        draw.text((4, 2),  plot_name + ": " + plot_expr[:26], font=get_font(11), fill=(150, 180, 255))
        draw.text((4, 15), "Az:" + str(td_azimuth) + " El:" + str(td_elevation),
                  font=get_font(10, False), fill=(100, 130, 200))
        draw.text((4, SH - 14), "Tap to return", font=get_font(10, False), fill=(80, 100, 140))
        draw_text_r(draw, SW - 10, 2, str(round(z_max, 2)), get_font(10, False), (200, 200, 200))
        draw_text_r(draw, SW - 10, SH - 14, str(round(z_min, 2)), get_font(10, False), (200, 200, 200))

        device.display(image)
        showing_3d = True

    except Exception as ex:
        notice = "Error: " + str(ex)[:34]


# ------------------------------------------------
#  CALCULATOR (Calculator / Scientific / Trigonometry)
# ------------------------------------------------
def evaluate():
    global expression, result_str, just_result
    if not expression:
        return
    try:
        ang  = math.pi / 180.0 if angle_deg else 1.0
        safe = {
            "pi": math.pi, "e": math.e,
            "sqrt": math.sqrt, "abs": abs,
            "log":  math.log,  "log10": math.log10, "log2": math.log2,
            "exp":  math.exp,
            "sin":  lambda v: math.sin(v * ang),
            "cos":  lambda v: math.cos(v * ang),
            "tan":  lambda v: math.tan(v * ang),
            "asin": lambda v: math.asin(v) / ang,
            "acos": lambda v: math.acos(v) / ang,
            "atan": lambda v: math.atan(v) / ang,
            "sinh": math.sinh, "cosh": math.cosh, "tanh": math.tanh,
        }
        result = eval(expression, {"__builtins__": {}}, safe)
        if isinstance(result, float):
            if result == int(result) and abs(result) < 1e15:
                result = int(result)
            else:
                result = float("{:.8g}".format(round(result, 8)))
        result_str  = str(result)
        expression  = result_str
        just_result = True
    except ZeroDivisionError:
        result_str  = "Div by 0"
        expression  = ""
        just_result = True
    except Exception:
        result_str  = "Error"
        expression  = ""
        just_result = True


def handle_calc(action):
    global expression, result_str, just_result, angle_deg

    if action == "TOGGLE_ANG":
        angle_deg = not angle_deg
        return
    if action == "DEL":
        expression = expression[:-1] if expression else ""
        result_str = expression or "0"
        return
    if action == "FACT":
        try:
            n          = int(float(expression))
            expression = str(math.factorial(n))
            result_str = expression
            just_result = True
        except Exception:
            result_str = "Error"
        return
    if action == "pi":
        expression += str(math.pi)
        result_str = expression
        just_result = False
        return
    if action == "e":
        expression += str(math.e)
        result_str = expression
        just_result = False
        return
    if action == "AC":
        expression = ""
        result_str = "0"
        just_result = False
        return
    if action == "NEG":
        if expression:
            expression = expression[1:] if expression[0] == "-" else "-" + expression
            result_str = expression
        return
    if action == "PCT":
        try:
            expression = str(eval(expression) / 100.0)
            result_str = expression
            just_result = True
        except Exception:
            result_str = "Error"
        return
    if action == "=":
        evaluate()
        return

    if action in ("+", "-", "*", "/", "%", "**", "(", ")"):
        if just_result and action not in ("+", "-", "*", "/", "%", "**"):
            expression = ""
        if expression and expression[-1] in ("+", "-", "*", "/") \
                and action in ("+", "-", "*", "/"):
            expression = expression[:-1]
        expression += action
        result_str = expression
        just_result = False
        return

    if action == ".":
        segs = expression.replace("+", " ").replace("-", " ") \
                         .replace("*", " ").replace("/", " ").split()
        last = segs[-1] if segs else ""
        if "." not in last:
            if not expression or expression[-1] in ("+", "-", "*", "/"):
                expression += "0"
            expression += "."
            result_str = expression
        just_result = False
        return

    if action.endswith("("):
        if just_result:
            expression = ""
            just_result = False
        expression += action
        result_str = expression
        return

    if just_result and action.isdigit():
        expression = action
        just_result = False
    else:
        expression += action
    result_str = expression


# ------------------------------------------------
#  CAS
# ------------------------------------------------
def run_cas(op):
    global cas_show, cas_value
    if not HAS_SYMPY:
        cas_show, cas_value = "sympy not installed", ""
        return
    if not cas_expr.strip():
        cas_show, cas_value = "Enter an expression first", ""
        return
    try:
        v    = sp.Symbol(cas_var)
        expr = parse_expr(cas_expr.replace("^", "**"),
                          local_dict=CAS_LOCALS, transformations=CAS_TRANSFORMS)

        if op == "DERIV":
            res = sp.diff(expr, v)
            label = "d/d" + cas_var
        elif op == "INTEG":
            res = sp.integrate(expr, v)
            label = INTEG + " d" + cas_var
        elif op == "SIMPLIFY":
            res = sp.simplify(expr)
            label = "simplify"
        elif op == "EXPAND":
            res = sp.expand(expr)
            label = "expand"
        elif op == "FACTOR":
            res = sp.factor(expr)
            label = "factor"
        elif op == "LIMIT":
            res = sp.limit(expr, v, 0)
            label = "lim " + cas_var + ARROW_R + "0"
        else:  # SOLVE  (expression = 0)
            sols = sp.solve(expr, v)
            cas_value = ""
            if sols:
                cas_show = cas_var + " = " + ", ".join(str(s) for s in sols)
            else:
                cas_show = "no solution"
            return

        text = str(res).replace("**", "^")
        cas_value = text
        cas_show  = label + " = " + text + (" + C" if op == "INTEG" else "")
    except Exception as ex:
        msg = str(ex)
        if isinstance(ex, (SyntaxError, TypeError)) or "EOF" in msg or "syntax" in msg.lower():
            msg = "Syntax error - check brackets"
        cas_show, cas_value = "Error: " + msg[:38], ""


def handle_cas(action):
    global cas_expr, cas_var, cas_show, cas_value

    if action.startswith("CT:"):
        cas_expr += action[3:]
        return
    if action == "CASX":
        cas_expr += "x"
        cas_var = "x"
        return
    if action == "CASX2":
        cas_expr += "x^2"
        cas_var = "x"
        return
    if action.startswith("CASVAR:"):
        cas_var = action[7:]
        cas_expr += cas_var
        return
    if action == "DEL":
        cas_expr = cas_expr[:-1]
        return
    if action == "AC":
        cas_expr = ""
        cas_show = ""
        cas_value = ""
        return
    if action == "TOEXPR":
        if cas_value:
            cas_expr = cas_value
            cas_show = ""
        else:
            cas_show = "Nothing to move (run an operation)"
        return
    if action in CAS_OPS:
        cas_show = "Working..."
        draw_ui()
        run_cas(action)


# ------------------------------------------------
#  GRAPH / 3D ACTIONS
# ------------------------------------------------
def handle_graph(action):
    global graph_expr, graph_xmode
    if action == "PLOT":
        draw_graph()
    elif action == "GCLR":
        graph_expr = ""
    elif action.startswith("GR:"):
        graph_xmode = action[3:]
    elif action.startswith("GT:"):
        graph_expr += action[3:]


def handle_3d(action):
    global td_func_name, td_func_expr, td_user_expr
    global td_azimuth, td_elevation, td_grid_res

    if action.startswith("T3:"):
        td_user_expr += action[3:]
        return
    if action == "T3CLR":
        td_user_expr = ""
        return
    if action.startswith("TD:"):
        cmd = action[3:]
        if cmd in TD_PRESETS:
            td_func_name = cmd
            td_func_expr = TD_PRESETS[cmd]
            td_user_expr = ""
        elif cmd == "RL":
            td_azimuth = (td_azimuth - 15) % 360
        elif cmd == "RR":
            td_azimuth = (td_azimuth + 15) % 360
        elif cmd == "TU":
            td_elevation = min(89, td_elevation + 10)
        elif cmd == "TD_":
            td_elevation = max(-89, td_elevation - 10)
        elif cmd == "FINE":
            td_grid_res = 25
        elif cmd == "COARSE":
            td_grid_res = 15
        elif cmd == "RESET":
            td_azimuth = 45
            td_elevation = 30
            td_grid_res = 20
        elif cmd == "PLOT":
            render_3d_surface()


def do_action(action):
    global active_submenu, notice
    notice = ""

    if action.startswith("M_"):
        active_submenu = action
        return
    if screen == "CAS":
        handle_cas(action)
    elif screen == "GRAPH":
        handle_graph(action)
    elif screen == "3D":
        handle_3d(action)
    else:
        handle_calc(action)


# ------------------------------------------------
#  TOUCH HELPERS  (UNCHANGED)
# ------------------------------------------------
def read_touch(cmd):
    r = spi_touch.xfer2([cmd, 0x00, 0x00])
    return ((r[1] << 8) | r[2]) >> 3


def map_value(value, in_min, in_max, out_min, out_max):
    if in_max == in_min:
        return out_min
    return int((value - in_min) * (out_max - out_min) / (in_max - in_min) + out_min)


def clamp(value, lo, hi):
    return max(lo, min(hi, value))


def is_touched():
    z1 = read_touch(0xB0)
    z2 = read_touch(0xC0)
    return (z1 - z2 + 4096) > 200


def get_screen_xy():
    raw_x = read_touch(0xD0)
    raw_y = read_touch(0x90)
    sx = map_value(raw_y, RAW_Y_MIN, RAW_Y_MAX, 0, SW)
    sy = map_value(raw_x, RAW_X_MIN, RAW_X_MAX, 0, SH)
    sx = SW - sx
    sy = SH - sy
    return clamp(sx, 0, SW), clamp(sy, 0, SH)


# ------------------------------------------------
#  NAVIGATION
# ------------------------------------------------
def wait_release(timeout=1.5):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            if not is_touched():
                return
        except Exception:
            return
        time.sleep(0.02)


def go_screen(name):
    global screen, active_submenu, notice, settings_msg
    screen = name
    active_submenu = None
    notice = ""
    if name == "SETTINGS":
        settings_msg = ""
        refresh_radio_states()
    draw_ui()
    wait_release()


def find_action(sx, sy):
    if screen == "HOME":
        boxes = HOME_BOXES
    elif screen == "SETTINGS":
        boxes = SETTINGS_BOXES
    else:
        boxes = KEYPAD_BOXES[screen]
    for (x1, y1, x2, y2, act) in boxes:
        if x1 <= sx <= x2 and y1 <= sy <= y2:
            return act
    return None


# ------------------------------------------------
#  STARTUP SCREENS
# ------------------------------------------------
def load_logo():
    for folder in (SCRIPT_DIR, os.getcwd()):
        path = os.path.join(folder, LOGO_FILE)
        if os.path.exists(path):
            try:
                img = Image.open(path).convert("RGB")
                scale = min(SW / float(img.width), SH / float(img.height))
                nw, nh = int(img.width * scale), int(img.height * scale)
                img = img.resize((nw, nh), Image.LANCZOS)
                canvas = Image.new("RGB", (SW, SH), (0, 0, 0))
                canvas.paste(img, ((SW - nw) // 2, (SH - nh) // 2))
                return canvas
            except Exception as ex:
                print("Logo error:", ex)
    print("Logo not found (" + LOGO_FILE + ") - using text logo")
    return None


def text_logo():
    img = Image.new("RGB", (SW, SH), (0, 0, 0))
    d = ImageDraw.Draw(img)
    draw_text_c(d, SW // 2, 100, "KUSHBOTICS", get_font(34), C_BRAND)
    draw_text_c(d, SW // 2, 140, "COMPUTER ALGEBRAIC SYSTEM", get_font(13), C_TEXT)
    return img


def draw_loading(msg, frac):
    image = Image.new("RGB", device.size, (0, 0, 0))
    d = ImageDraw.Draw(image)
    draw_text_c(d, SW // 2, 78, "KUSHBOTICS", get_font(30), C_BRAND)
    draw_text_c(d, SW // 2, 112, "Calculator", get_font(20), C_TEXT)
    bx1, bx2, by1, by2 = 60, SW - 60, 160, 170
    d.rectangle((bx1, by1, bx2, by2), outline=C_OUTLINE)
    d.rectangle((bx1 + 2, by1 + 2, bx1 + 2 + int((bx2 - bx1 - 4) * frac), by2 - 2), fill=C_BRAND)
    draw_text_c(d, SW // 2, 188, msg, get_font(11, False), C_TEXDIM)
    draw_text_c(d, SW // 2, SH - 12, "v" + APP_VERSION, get_font(10, False), (60, 70, 100))
    device.display(image)


def show_splash():
    logo = load_logo() or text_logo()
    black = Image.new("RGB", (SW, SH), (0, 0, 0))
    for i in range(1, 9):
        device.display(Image.blend(black, logo, i / 8.0))
        time.sleep(0.03)
    time.sleep(1.6)

    t0 = time.time()
    steps = [("Loading numpy...", load_numpy),
             ("Loading CAS engine...", load_sympy),
             ("Checking radios...", refresh_radio_states)]
    for i, (msg, fn) in enumerate(steps):
        draw_loading(msg, i / float(len(steps)))
        fn()
    draw_loading("Ready", 1.0)
    time.sleep(max(0.0, 1.0 - (time.time() - t0)))


# ------------------------------------------------
#  MAIN LOOP
# ------------------------------------------------
DEBOUNCE = 0.28


def main():
    global active_submenu

    init_hardware()
    print(APP_NAME, APP_VERSION)
    show_splash()
    print("numpy:", HAS_NUMPY, "  sympy:", HAS_SYMPY)
    go_screen("HOME")

    last_action = ""
    last_time   = 0.0

    try:
        while True:
            try:
                if not is_touched():
                    time.sleep(poll_delay())
                    continue

                sx, sy = get_screen_xy()
                if DEBUG_TOUCH:
                    print("X:" + str(sx) + " Y:" + str(sy))

                # full-screen graph / 3D: any tap returns to its keypad
                if showing_graph or showing_3d:
                    wait_release()
                    draw_ui()
                    time.sleep(0.15)
                    continue

                # modal submenu
                if active_submenu:
                    action = None
                    for b in submenu_hitboxes:
                        if b["x1"] <= sx <= b["x2"] and b["y1"] <= sy <= b["y2"]:
                            action = b["action"]
                            break
                    active_submenu = None
                    if action:
                        do_action(action)
                    if not showing_graph and not showing_3d:
                        draw_ui()
                    time.sleep(0.15)
                    continue

                action = find_action(sx, sy)
                if action is None:
                    time.sleep(0.02)
                    continue

                now = time.time()
                if action == last_action and (now - last_time) < DEBOUNCE:
                    time.sleep(0.02)
                    continue
                last_action = action
                last_time   = now

                if action == "NAV_HOME":
                    go_screen("HOME")
                    continue
                if action.startswith("NAV:"):
                    go_screen(action[4:])
                    continue

                if screen == "SETTINGS":
                    handle_settings(action)
                    draw_ui()
                    wait_release()
                    continue

                draw_ui(highlight=action)
                time.sleep(0.07)
                do_action(action)
                if not showing_graph and not showing_3d:
                    draw_ui()
                time.sleep(0.02)

            except Exception as e:
                print("Error: " + str(e))
                time.sleep(0.1)
    finally:
        if power_save:
            apply_power_save(False)


# ------------------------------------------------
#  AUTOSTART  (systemd)
# ------------------------------------------------
def install_autostart(run_as_root=False):
    if os.geteuid() != 0:
        print("Re-running with sudo...")
        os.execvp("sudo", ["sudo", sys.executable, SCRIPT_PATH] + sys.argv[1:])

    user = "root" if run_as_root else os.environ.get("SUDO_USER", "root")
    unit = (
        "[Unit]\n"
        "Description=Kushbotics Calculator\n"
        "After=multi-user.target\n\n"
        "[Service]\n"
        "Type=simple\n"
        "User=" + user + "\n"
        "WorkingDirectory=" + SCRIPT_DIR + "\n"
        "Environment=PYTHONUNBUFFERED=1\n"
        "ExecStart=" + sys.executable + " " + SCRIPT_PATH + "\n"
        "Restart=on-failure\n"
        "RestartSec=3\n\n"
        "[Install]\n"
        "WantedBy=multi-user.target\n"
    )
    with open(SERVICE_PATH, "w") as f:
        f.write(unit)
    subprocess.run(["systemctl", "daemon-reload"], check=False)
    subprocess.run(["systemctl", "enable", SERVICE_NAME + ".service"], check=False)
    print("Autostart installed (runs as user: " + user + ").")
    print("It will start on the next boot.")
    print("Start now:   sudo systemctl start " + SERVICE_NAME)
    print("Stop:        sudo systemctl stop " + SERVICE_NAME)
    print("(Close Thonny's run first - only one program can use the screen.)")


def uninstall_autostart():
    if os.geteuid() != 0:
        os.execvp("sudo", ["sudo", sys.executable, SCRIPT_PATH] + sys.argv[1:])
    subprocess.run(["systemctl", "disable", "--now", SERVICE_NAME + ".service"], check=False)
    if os.path.exists(SERVICE_PATH):
        os.remove(SERVICE_PATH)
    subprocess.run(["systemctl", "daemon-reload"], check=False)
    print("Autostart removed.")


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--install-autostart" in args:
        install_autostart("--root" in args)
    elif "--uninstall-autostart" in args:
        uninstall_autostart()
    elif "--help" in args or "-h" in args:
        print(__doc__)
    else:
        main()
