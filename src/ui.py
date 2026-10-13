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
