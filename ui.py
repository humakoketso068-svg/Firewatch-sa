"""Shared theme colours and small UI helpers."""

import flet as ft

# ---------------------------------------------------------------------------
# Theme
# ---------------------------------------------------------------------------

BG = "#F5F6F7"
PANEL = "#FFFFFF"
LINE = "#E2E5E8"
LINE_SOFT = "#EDEFF1"
TEXT = "#15181B"
DIM = "#5B636B"
FAINT = "#87909A"

RISK = {
    "low": "#3F9560",
    "moderate": "#C99A1E",
    "high": "#DB7423",
    "extreme": "#D13B2E",
}
CONTAINED = "#A3ABB2"
EMERGENCY = "#D13B2E"
EMERGENCY_DARK = "#A82A1F"
DARK = "#1B1F23"
INFO_BLUE = "#2F6FED"
WIND = "#3B84A0"
MOIST = "#4F9A5B"
MAP_BG = "#F4F6F7"
MAP_LINE = "#E3E7EA"
LAND = "#E4EAE5"
LAND_EDGE = "#9FAAA3"
PROVINCE_TEXT = "#A3ACB3"
HOTSPOT = "#E8590C"          # NASA satellite hotspot

FEED_COLOR = {
    "extreme": RISK["extreme"],
    "high": RISK["high"],
    "info": WIND,
    "contained": "#7C848C",
}

COMPASS = [
    "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"
]


def compass_dir(deg):
    return COMPASS[int(round(deg / 22.5)) % 16]


def fmt_coord(lat, lon):
    """-25.6958, 27.2956 -> '25.6958° S, 27.2956° E'"""
    return f"{abs(lat):.4f}° {'S' if lat < 0 else 'N'}, {abs(lon):.4f}° {'E' if lon >= 0 else 'W'}"


def age_text(ts):
    """'12 min ago', '3 h ago' for an epoch timestamp."""
    import time
    secs = max(0, time.time() - ts)
    if secs < 90:
        return "just now"
    if secs < 5400:
        return f"{round(secs / 60)} min ago"
    if secs < 172800:
        return f"{round(secs / 3600)} h ago"
    return f"{round(secs / 86400)} days ago"


def txt(value, size=13, color=DIM, bold=False, font_family=None):
    return ft.Text(
        str(value),
        size=size,
        color=color,
        weight=ft.FontWeight.BOLD if bold else ft.FontWeight.NORMAL,
        font_family=font_family,
    )



def card(content, padding=14, expand=False, width=None, height=None):
    return ft.Container(
        content=content,
        bgcolor=PANEL,
        border=ft.Border.all(1, LINE),
        border_radius=8,
        padding=padding,
        expand=expand,
        width=width,
        height=height,
    )


def chip(label, color):
    return ft.Container(
        content=txt(label.capitalize(), 11, color, bold=True),
        border=ft.Border.all(1, color),
        border_radius=6,
        padding=ft.Padding.symmetric(horizontal=9, vertical=4),
    )


def dot(color, size=8):
    return ft.Container( 
        width=size,
        height=size,
        bgcolor=color,
        border_radius=size / 2,
    )



def primary_button(label, on_click, icon=None, color=EMERGENCY):
    """Solid coloured button (plain FilledButton, same style family as the original app)."""
    return ft.FilledButton(
        label, icon=icon, on_click=on_click,
        style=ft.ButtonStyle(bgcolor=color, color="#FFFFFF"),
    )


def open_url(page, url):
    """Open a link or phone call (tel:112) from a button. Works on desktop, phone and web."""
    async def go():
        launcher = getattr(page, "_fw_launcher", None)
        if launcher is None:
            launcher = ft.UrlLauncher()
            page.services.append(launcher)
            page._fw_launcher = launcher
        await launcher.launch_url(url)
    page.run_task(go)

# Dashboard shell colours
NAVY = "#0D1B3A"
NAVY_LINE = "#1F3160"
NAV_TEXT = "#B7C2DD"
GRAD_A = "#2F6FED"
GRAD_B = "#5547D9"
PAGE_BG = "#F5F7FB"
