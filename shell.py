"""
The app shell: a dashboard layout that adapts to the device.

  desktop (>= 1100 px)  dark left menu, top bar with search, welcome hero, stat cards,
                        map preview, latest updates and a recent-alerts column
  tablet  (>= 700 px)   the same with a slim icon-only menu
  phone   (>= 300 px)   top bar, bottom navigation, floating SOS button
  watch   (< 300 px)    a glance view: status, nearest fire, one big SOS button, call 112

Flet apps cannot be installed on Apple Watch or Wear OS. The watch layout is what appears when
the page is opened on a very small screen (a small watch browser, or a narrow window). Alerts
reach a smartwatch the normal way: SMS, email and Telegram notifications are mirrored from the
paired phone.
"""

from datetime import datetime

import flet as ft

import config
import dialogs
import firms
import places
import reports
import screens
from ui import (
    BG, CONTAINED, DIM, EMERGENCY, FAINT, GRAD_A, HOTSPOT, GRAD_B, INFO_BLUE, LINE, LINE_SOFT, NAV_TEXT, NAVY,
    PAGE_BG, PANEL, RISK, TEXT, card, dot, open_url, txt, chip,
)

SELECTED_BG = "#E8EEFC"
GRADIENT = ft.LinearGradient(begin=ft.Alignment.CENTER_LEFT, end=ft.Alignment.CENTER_RIGHT, colors=[GRAD_A, GRAD_B])


def backdrop(name="bg_hills.png"):
    """A picture from assets/ used as a background. None if the file is missing."""
    try:
        import base64
        import pathlib
        data = (pathlib.Path(__file__).parent / "assets" / name).read_bytes()
        return ft.DecorationImage(src=base64.b64encode(data).decode("ascii"), fit=ft.BoxFit.COVER,
                                  alignment=ft.Alignment.BOTTOM_CENTER)
    except Exception:
        return None


def mode_for(width, height=None):
    """'watch', 'phone', 'tablet' or 'desktop' from the window size."""
    width = width or 1000
    if width < 300 or (width < 380 and height and height < 380):
        return "watch"
    if width < 700:
        return "phone"
    if width < 1100:
        return "tablet"
    return "desktop"


def initials(name):
    parts = [p for p in name.split() if p]
    return (parts[0][0] + (parts[-1][0] if len(parts) > 1 else "")).upper() if parts else "?"


def clean(text):
    return (text or "").replace("[b]", "").replace("[/b]", "")


class StatusPill(ft.Container):
    def __init__(self):
        self.dot_control = dot(RISK["low"], 8)
        self.label = txt("System online", 12, TEXT, bold=True)
        super().__init__(
            content=ft.Row([self.dot_control, self.label], spacing=8, tight=True),
            border=ft.Border.all(1, LINE), border_radius=16, bgcolor=PANEL,
            padding=ft.Padding.symmetric(horizontal=12, vertical=6))

    def set_state(self, alert, label):
        self.label.value = label
        self.dot_control.bgcolor = RISK["extreme"] if alert else RISK["low"]
        self.label.color = RISK["extreme"] if alert else TEXT
        self.border = ft.Border.all(1, RISK["extreme"] if alert else LINE)


# ---------------------------------------------------------------------------
# Top bar
# ---------------------------------------------------------------------------

class Header(ft.Container):
    """Top bar: search, data-mode chip, notification bell and the account menu."""

    def __init__(self, app):
        self.app = app
        self.mobile = False
        self.mode = "desktop"
        self.brand = ft.Row(
            [ft.Container(content=ft.Icon(ft.Icons.LOCAL_FIRE_DEPARTMENT, color="#FFFFFF", size=16),
                          width=28, height=28, bgcolor=EMERGENCY, border_radius=14, alignment=ft.Alignment.CENTER),
             txt("Firewatch", 17, TEXT, bold=True)], spacing=8, tight=True)
        self.search = ft.TextField(
            hint_text="Search a town, township or village…", prefix_icon=ft.Icons.SEARCH, dense=True,
            border_radius=22, text_size=13.5, bgcolor="#F1F4FA", border_color="#F1F4FA", expand=True,
            on_submit=self._search, content_padding=ft.Padding.symmetric(horizontal=8, vertical=0))
        self.search_box = ft.Container(content=self.search, expand=True, padding=ft.Padding.only(right=24))
        self.mode_chip = ft.Container(
            content=txt("Simulation", 11.5, DIM, bold=True), border=ft.Border.all(1, LINE),
            border_radius=14, padding=ft.Padding.symmetric(horizontal=10, vertical=4), bgcolor=PANEL)
        self.bell_dot = ft.Container(width=9, height=9, border_radius=5, bgcolor=EMERGENCY, right=7, top=7, visible=False)
        self.bell = ft.Stack([ft.IconButton(ft.Icons.NOTIFICATIONS_NONE, icon_size=24, tooltip="Alerts",
                                            on_click=lambda e: app.shell.navigate("alerts")), self.bell_dot],
                             width=48, height=48)
        self.avatar = txt("?", 13, "#FFFFFF", bold=True)
        self.user_name = txt("Sign in", 13, TEXT, bold=True)
        self.menu = ft.PopupMenuButton(
            tooltip="Account", items=[],
            content=ft.Row([ft.Container(content=self.avatar, width=34, height=34, border_radius=17, bgcolor="#8C7BFF",
                                         alignment=ft.Alignment.CENTER),
                            self.user_name, ft.Icon(ft.Icons.KEYBOARD_ARROW_DOWN, size=18, color=DIM)],
                           spacing=8, tight=True))
        self.row = ft.Row([], vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=10)
        super().__init__(content=self.row, bgcolor=PANEL, padding=ft.Padding.symmetric(horizontal=16, vertical=8),
                         border=ft.Border.only(bottom=ft.BorderSide(1, LINE)), height=64)
        self.set_user(None)

    def _search(self, e):
        q = (self.search.value or "").strip()
        if q:
            self.app.shell.navigate("map")
            self.app.map.search.value = q
            self.app.map._on_search_submit(None)
            self.app.page.update()

    def set_live(self, live):
        self.mode_chip.content = txt("NASA live data" if live else "Simulation", 11.5,
                                     RISK["low"] if live else DIM, bold=True)
        self.mode_chip.border = ft.Border.all(1, RISK["low"] if live else LINE)

    def set_alert(self, active):
        self.bell_dot.visible = bool(active)

    def apply_mode(self, mode):
        self.mode = mode
        self.mobile = mode in ("phone", "watch")
        self.user_name.visible = mode == "desktop"
        parts = []
        if mode == "phone":
            parts = [self.brand, ft.Container(expand=True)]
        else:
            parts = [self.search_box]
        if mode == "desktop":
            parts.append(self.mode_chip)
        parts += [self.bell, self.menu]
        self.row.controls = parts
        self.padding = ft.Padding.symmetric(horizontal=10 if mode == "phone" else 20, vertical=8)

    def set_user(self, user):
        app = self.app
        self.avatar.value = initials(user["name"]) if user else "?"
        self.user_name.value = user["name"] if user else "Sign in"
        if user is None:
            items = [
                ft.PopupMenuItem(content="Log in", icon=ft.Icons.LOGIN, on_click=lambda e: dialogs.show_login(app)),
                ft.PopupMenuItem(content="Sign up", icon=ft.Icons.PERSON_ADD, on_click=lambda e: dialogs.show_signup(app)),
            ]
        else:
            items = [
                ft.PopupMenuItem(content=f"Signed in as {user['name'].split()[0]}", icon=ft.Icons.ACCOUNT_CIRCLE, disabled=True),
                ft.PopupMenuItem(content="My profile", icon=ft.Icons.PERSON, on_click=lambda e: dialogs.show_profile(app)),
                ft.PopupMenuItem(content="Alert settings and contacts", icon=ft.Icons.TUNE,
                                 on_click=lambda e: screens.show_settings(app)),
                ft.PopupMenuItem(content="Log out", icon=ft.Icons.LOGOUT,
                                 on_click=lambda e: (app.set_user(None), app.toast("You have been logged out."))),
            ]
        items.append(ft.PopupMenuItem(content="Reset simulation", icon=ft.Icons.REFRESH, on_click=app.reset))
        self.menu.items = items


# ---------------------------------------------------------------------------
# Dark left menu and bottom bar
# ---------------------------------------------------------------------------

class NavItem(ft.Container):
    def __init__(self, icon, label, on_click, danger=False):
        self.danger = danger
        self.icon_control = ft.Icon(icon, size=20, color=NAV_TEXT)
        self.label_control = txt(label, 14, NAV_TEXT)
        self.badge_text = txt("", 11, "#FFFFFF", bold=True)
        self.badge_box = ft.Container(content=self.badge_text, bgcolor=EMERGENCY, border_radius=11, width=22, height=22,
                                      alignment=ft.Alignment.CENTER, visible=False)
        self.spacer = ft.Container(expand=True)
        super().__init__(
            content=ft.Row([self.icon_control, self.label_control, self.spacer, self.badge_box], spacing=12),
            padding=ft.Padding.symmetric(horizontal=14, vertical=11), border_radius=10, ink=True,
            on_click=on_click, tooltip=label)

    def set_selected(self, selected):
        self.gradient = GRADIENT if selected else None
        self.icon_control.color = "#FFFFFF" if selected else NAV_TEXT
        self.label_control.color = "#FFFFFF" if selected else NAV_TEXT
        self.label_control.weight = ft.FontWeight.W_600 if selected else None

    def set_badge(self, n):
        self.badge_text.value = str(n)
        self.badge_box.visible = bool(n) and not self.compact_on

    compact_on = False

    def set_compact(self, compact):
        self.compact_on = compact
        self.label_control.visible = not compact
        self.spacer.visible = not compact
        if compact:
            self.badge_box.visible = False
        self.content.alignment = ft.MainAxisAlignment.CENTER if compact else ft.MainAxisAlignment.START
        self.padding = ft.Padding.symmetric(horizontal=0 if compact else 14, vertical=11)


class Sidebar(ft.Container):
    def __init__(self, shell):
        self.shell = shell
        self.items = {}
        self.compact = False

        def page(key, icon, label):
            item = NavItem(icon, label, lambda e, k=key: shell.navigate(k))
            self.items[key] = item
            return item

        self.brand_text = txt("Firewatch", 24, "#FFFFFF", bold=True)
        self.brand = ft.Row([ft.Icon(ft.Icons.LOCAL_FIRE_DEPARTMENT, color="#FF7A45", size=34), self.brand_text],
                            spacing=8, tight=True)
        self.sos_label = txt("Send SOS", 14, "#FFFFFF", bold=True)
        self.sos_call = txt("Call 112", 12, NAV_TEXT)
        self.sos_button = ft.Container(
            content=ft.Row([ft.Icon(ft.Icons.WARNING_AMBER, color="#FFFFFF", size=22), self.sos_label],
                           spacing=10, alignment=ft.MainAxisAlignment.CENTER),
            bgcolor=EMERGENCY, border_radius=10, padding=ft.Padding.symmetric(horizontal=10, vertical=14), ink=True,
            tooltip="Emergency alert to fire stations", on_click=lambda e: dialogs.show_emergency(shell.app))
        self.call_button = ft.Container(
            content=ft.Row([ft.Icon(ft.Icons.CALL, color=NAV_TEXT, size=16), self.sos_call], spacing=8,
                           alignment=ft.MainAxisAlignment.CENTER),
            border=ft.Border.all(1, "#5B6C95"), border_radius=10, padding=ft.Padding.symmetric(horizontal=10, vertical=9),
            ink=True, on_click=lambda e: open_url(shell.app.page, "tel:112"), tooltip="Call 112")
        self.tag = txt("Safer Communities.\nGreener Tomorrow.", 12, "#FFFFFF", bold=True)
        self.tag.text_align = ft.TextAlign.CENTER
        self.tag_box = ft.Container(
            content=ft.Column([self.tag], spacing=6,
                              horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            alignment=ft.Alignment.CENTER, padding=ft.Padding.only(bottom=8))
        self.column = ft.Column([
            ft.Container(content=self.brand, padding=ft.Padding.only(left=8, top=6, bottom=24)),
            page("overview", ft.Icons.HOME_FILLED, "Overview"),
            page("map", ft.Icons.MAP_OUTLINED, "Map"),
            page("alerts", ft.Icons.NOTIFICATIONS_NONE, "Alerts"),
            page("reports", ft.Icons.DESCRIPTION_OUTLINED, "Reports"),
            page("settings", ft.Icons.SETTINGS_OUTLINED, "Settings"),
        ], spacing=6, scroll=ft.ScrollMode.AUTO, expand=True)
        super().__init__(content=ft.Column([self.column, self.sos_button, self.call_button, self.tag_box], spacing=8), width=256, bgcolor=NAVY,
                         image=backdrop("side_fire.jpg"), padding=ft.Padding.symmetric(horizontal=14, vertical=14))

    def set_compact(self, compact):
        self.compact = compact
        self.width = 76 if compact else 256
        for item in self.items.values():
            item.set_compact(compact)
        self.brand_text.visible = not compact
        self.tag_box.visible = not compact
        self.sos_label.visible = not compact
        self.sos_call.visible = not compact

    def select(self, key):
        key = key if key in self.items else "settings"
        for k, item in self.items.items():
            item.set_selected(k == key)

    def set_alerts(self, n):
        self.items["alerts"].set_badge(n)


class BottomBar(ft.Container):
    """Phone navigation."""

    def __init__(self, shell):
        self.shell = shell
        self.buttons = {}

        def button(key, icon, label):
            icon_c = ft.Icon(icon, size=22, color=DIM)
            label_c = txt(label, 10.5, DIM)
            box = ft.Container(content=ft.Column([icon_c, label_c], spacing=1, tight=True,
                                                 horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                               expand=True, ink=True, on_click=lambda e: shell.navigate(key),
                               padding=ft.Padding.symmetric(vertical=7))
            self.buttons[key] = (icon_c, label_c)
            return box

        super().__init__(
            content=ft.Row([
                button("overview", ft.Icons.HOME_FILLED, "Home"),
                button("map", ft.Icons.MAP_OUTLINED, "Map"),
                button("alerts", ft.Icons.NOTIFICATIONS_NONE, "Alerts"),
                button("reports", ft.Icons.DESCRIPTION_OUTLINED, "Reports"),
                button("settings", ft.Icons.SETTINGS_OUTLINED, "More"),
            ], spacing=0),
            bgcolor=PANEL, border=ft.Border.only(top=ft.BorderSide(1, LINE)), height=58)

    def select(self, key):
        key = key if key in self.buttons else "settings"
        for k, (icon_c, label_c) in self.buttons.items():
            on = k == key
            icon_c.color = INFO_BLUE if on else DIM
            label_c.color = INFO_BLUE if on else DIM


# ---------------------------------------------------------------------------
# Small building blocks
# ---------------------------------------------------------------------------

def link_button(label, fn):
    return ft.TextButton(label, on_click=lambda e: fn(),
                         style=ft.ButtonStyle(color=INFO_BLUE, padding=ft.Padding.symmetric(horizontal=4, vertical=0)))


def panel(title, icon, body, action=None, pad=18):
    """White rounded card with an icon title row and an optional 'View all' link."""
    head = [ft.Icon(icon, color=DIM, size=22), txt(title, 16, TEXT, bold=True), ft.Container(expand=True)]
    if action:
        head.append(link_button(*action))
    return ft.Container(content=ft.Column([ft.Row(head, spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER), body],
                                          spacing=10, tight=True),
                        bgcolor=PANEL, border=ft.Border.all(1, LINE), border_radius=16, padding=pad)


class StatCard(ft.Container):
    def __init__(self, icon, color, tint, label):
        self.base = None
        self.value_c = txt("-", 28, TEXT, bold=True)
        self.sub_icon = ft.Icon(ft.Icons.REMOVE, size=14, color=DIM)
        self.sub_c = txt("", 12, DIM)
        super().__init__(
            content=ft.Column([
                ft.Container(content=ft.Icon(icon, color=color, size=24), width=48, height=48, border_radius=24,
                             bgcolor=tint, alignment=ft.Alignment.CENTER),
                txt(label, 13.5, TEXT, bold=True), self.value_c,
                ft.Row([self.sub_icon, ft.Container(content=self.sub_c, expand=True)], spacing=4)], spacing=6, tight=True),
            bgcolor=PANEL, border=ft.Border.all(1, LINE), border_radius=16, padding=18)

    def set(self, value, sub, icon=ft.Icons.REMOVE, color=DIM):
        self.value_c.value = str(value)
        self.sub_c.value = sub
        self.sub_c.color = color
        self.sub_icon.icon = icon
        self.sub_icon.color = color

    def set_delta(self, value, bad_when_up=True, unit=""):
        """Show the change since the app was opened (the first value seen)."""
        if self.base is None:
            self.base = value
        d = value - self.base
        self.value_c.value = f"{value}{unit}"
        if d == 0:
            self.sub_c.value, self.sub_icon.icon, color = "No change since you opened this", ft.Icons.REMOVE, DIM
        else:
            up = d > 0
            color = (RISK["extreme"] if up else RISK["low"]) if bad_when_up else (RISK["low"] if up else RISK["extreme"])
            self.sub_c.value = f"{'+' if up else ''}{d} since you opened this"
            self.sub_icon.icon = ft.Icons.NORTH_EAST if up else ft.Icons.SOUTH_EAST
        self.sub_c.color = self.sub_icon.color = color


ICON_FOR = {"extreme": (ft.Icons.LOCAL_FIRE_DEPARTMENT, "#E5484D", "#FDE7E7", "High"),
            "high": (ft.Icons.WARNING_AMBER, "#F59E0B", "#FEF1D6", "Medium"),
            "info": (ft.Icons.INFO_OUTLINE, "#3B82F6", "#E1ECFE", "Info"),
            "contained": (ft.Icons.CHECK_CIRCLE_OUTLINE, "#22A06B", "#DDF3E8", "Resolved")}


def alert_row(entry, on_click=None, big=False):
    icon, color, tint, label = ICON_FOR.get(entry["cls"], ICON_FOR["info"])
    size = 44 if big else 36
    right = [chip(label, color)] if big else []
    return ft.Container(
        content=ft.Row([
            ft.Container(content=ft.Icon(icon, color=color, size=22 if big else 18), width=size, height=size,
                        border_radius=size // 2, bgcolor=tint, alignment=ft.Alignment.CENTER),
            ft.Column([txt(clean(entry["text"]), 13.5 if big else 13, TEXT, bold=big),
                       txt(f'{entry["tag"]} · {entry["ts"]}', 11.5, FAINT)], spacing=2, expand=True),
            *right, ft.Icon(ft.Icons.CHEVRON_RIGHT, size=18, color=FAINT)],
            spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        padding=ft.Padding.symmetric(vertical=11), ink=True, on_click=on_click,
        border=ft.Border.only(bottom=ft.BorderSide(1, LINE_SOFT)))


def empty_note(text):
    return ft.Container(content=txt(text, 13, DIM), padding=ft.Padding.symmetric(vertical=14))


def side_actions(title, lines, buttons):
    return ft.Container(
        content=ft.Column([txt(title, 16, TEXT, bold=True), *[txt(t, 12.5, DIM) for t in lines], *buttons],
                          spacing=10, tight=True),
        bgcolor=PANEL, border=ft.Border.all(1, LINE), border_radius=16, padding=18)


def solid(label, icon, fn, color=INFO_BLUE):
    return ft.FilledButton(label, icon=icon, on_click=lambda e: fn(), style=ft.ButtonStyle(bgcolor=color, color="#FFFFFF"))


def outline(label, icon, fn):
    return ft.OutlinedButton(label, icon=icon, on_click=lambda e: fn())


def need_login(app, fn):
    return lambda: (fn() if app.user else dialogs.show_login(app))


def stat_row(cards):
    return ft.ResponsiveRow([ft.Container(content=c, col={"xs": 6, "md": 3}) for c in cards], spacing=14, run_spacing=14)


def compass(deg):
    from ui import compass_dir
    return compass_dir(deg)


# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------

class Dashboard(ft.Column):
    """Greeting, date card, four stat cards, live map preview and the recent-alerts column."""

    def __init__(self, shell):
        app = shell.app
        self.shell = shell
        go = shell.navigate
        self.greeting = txt("Good morning", 30, TEXT, bold=True)
        self.sub = txt("Here's what's happening with the wildfire risk in your area.", 14, DIM)
        self.date = txt("", 13, TEXT)
        self.time = txt("", 22, TEXT, bold=True)
        self.wx = txt("", 12.5, DIM)
        date_card = ft.Container(
            content=ft.Row([ft.Column([self.date, ft.Row([ft.Icon(ft.Icons.WB_SUNNY_OUTLINED, size=18, color="#F59E0B"), self.wx],
                                                         spacing=6, tight=True)], spacing=6, expand=True), self.time],
                           vertical_alignment=ft.CrossAxisAlignment.CENTER),
            bgcolor=PANEL, border=ft.Border.all(1, LINE), border_radius=14, padding=ft.Padding.symmetric(horizontal=16, vertical=12))
        header = ft.ResponsiveRow([
            ft.Container(col={"xs": 12, "md": 8}, content=ft.Column([self.greeting, self.sub], spacing=4, tight=True)),
            ft.Container(col={"xs": 12, "md": 4}, content=date_card)], spacing=14, run_spacing=10,
            vertical_alignment=ft.CrossAxisAlignment.CENTER)

        self.s_fires = StatCard(ft.Icons.LOCAL_FIRE_DEPARTMENT, "#E5484D", "#FDE7E7", "Active Fires")
        self.s_risk = StatCard(ft.Icons.WARNING_AMBER, "#F59E0B", "#FEF1D6", "High Risk Areas")
        self.s_regions = StatCard(ft.Icons.SHIELD_OUTLINED, "#22A06B", "#DDF3E8", "Monitored Regions")
        self.s_wind = StatCard(ft.Icons.CLOUD_OUTLINED, "#3B82F6", "#E1ECFE", "Weather Conditions")

        self.mini = app.mini
        self.mini.search_panel.visible = False
        self.mini_holder = ft.Container(content=self.mini, height=380, border_radius=12, clip_behavior=ft.ClipBehavior.HARD_EDGE)
        map_card = panel("Live Wildfire Map", ft.Icons.MAP_OUTLINED, self.mini_holder, ("View full map", lambda: go("map")), pad=14)
        self.alerts_list = ft.Column(spacing=0, tight=True)
        alerts_card = panel("Recent Alerts", ft.Icons.NOTIFICATIONS_NONE, self.alerts_list, ("View all", lambda: go("alerts")))
        self.pill = StatusPill()
        main = ft.ResponsiveRow([
            ft.Container(col={"xs": 12, "lg": 8}, content=map_card),
            ft.Container(col={"xs": 12, "lg": 4}, content=alerts_card)], spacing=14, run_spacing=14,
            vertical_alignment=ft.CrossAxisAlignment.START)
        super().__init__([header, stat_row([self.s_fires, self.s_risk, self.s_regions, self.s_wind]), main], spacing=16)

    def set_compact(self, compact):
        self.greeting.size = 24 if compact else 30
        self.mini_holder.height = 280 if compact else 380

    def render(self, state, user):
        zones = state["zones"]
        active = [f for f in state["fires"] if not f["contained"]]
        high = [z for z in zones if z["risk_level"] in ("high", "extreme")]
        now = datetime.now()
        part = "morning" if now.hour < 12 else "afternoon" if now.hour < 18 else "evening"
        self.greeting.value = f"Good {part}, {user['name'].split()[0]}" if user else f"Good {part}"
        self.sub.value = ("Here's what's happening with the wildfire risk in your area." if user
                          else "Here's what's happening across South Africa. Sign in to follow your own town.")
        self.date.value = now.strftime("%a, %d %b %Y")
        self.time.value = now.strftime("%H:%M")
        wind = state["wind"]
        self.wx.value = f'Wind {round(wind["speed"])} km/h from {compass(wind["dir"])}'
        self.s_fires.set_delta(len(active))
        self.s_risk.set_delta(len(high))
        self.s_regions.set(len(zones), "Sensor towns online", ft.Icons.REMOVE, DIM)
        top = max(zones, key=lambda z: z["risk"])
        self.s_wind.set(f'{round(wind["speed"])} km/h', f'From {compass(wind["dir"])} · highest risk {top["name"].split(" (")[0]}',
                        ft.Icons.AIR, DIM)
        alerts = [e for e in state["feed"] if e["cls"] in ("extreme", "high")][:5] or state["feed"][:4]
        self.alerts_list.controls = [alert_row(e, lambda ev: self.shell.navigate("alerts")) for e in alerts] or [empty_note("No alerts right now.")]


# ---------------------------------------------------------------------------
# Map
# ---------------------------------------------------------------------------

LAYERS = [("fires", "Fire locations"), ("zones", "Risk zones (sensor towns)"), ("hotspots", "NASA satellite hotspots"),
          ("reports", "Citizen reports"), ("spread", "Projected spread"), ("notices", "Station notices")]
RISK_OPTIONS = [("all", "All risk levels"), ("high", "High and extreme"), ("moderate", "Moderate"), ("low", "Low")]


class MapPage(ft.Column):
    """Big map, filters, layer controls, legend and the zones list."""

    def __init__(self, shell):
        app = shell.app
        self.app = app
        self.map = app.map
        provinces = sorted({z["province"] for z in app.sim.zones})
        self.region = ft.Dropdown(label="Region", value="all", dense=True, border_radius=8, text_size=13, width=190,
                                  options=[ft.DropdownOption(key="all", text="All regions")] +
                                          [ft.DropdownOption(key=p, text=p) for p in provinces])
        self.region.on_select = self._on_region
        self.risk = ft.Dropdown(label="Risk", value="all", dense=True, border_radius=8, text_size=13, width=190,
                                options=[ft.DropdownOption(key=k, text=t) for k, t in RISK_OPTIONS])
        self.risk.on_select = self._on_risk
        self.live_chip = ft.Container(content=txt("Simulation", 12, "#FFFFFF", bold=True), bgcolor=GRAD_A, border_radius=8,
                                      padding=ft.Padding.symmetric(horizontal=14, vertical=9))
        self.controls_row = ft.Row([self.region, self.risk,
                                    solid("Report smoke or fire", ft.Icons.ADD_LOCATION_ALT, app.start_report),
                                    self.live_chip], spacing=10, wrap=True, run_spacing=8, alignment=ft.MainAxisAlignment.END)
        self.map_holder = ft.Container(content=self.map, height=620, border_radius=12, clip_behavior=ft.ClipBehavior.HARD_EDGE)
        self.map_card = ft.Container(content=ft.Column([self.map_holder, app.data_note], spacing=8), bgcolor=PANEL,
                                     border=ft.Border.all(1, LINE), border_radius=16, padding=12)

        def check(key, label):
            return ft.Checkbox(label=label, value=True, on_change=lambda e, k=key: self._toggle(k, e.control.value))
        layers = panel("Layer Controls", ft.Icons.LAYERS_OUTLINED,
                       ft.Column([check(k, t) for k, t in LAYERS], spacing=0, tight=True))

        def key(color_dot, label):
            return ft.Row([color_dot, txt(label, 12.5, TEXT)], spacing=8, tight=True)
        legend = panel("Map Legend", ft.Icons.INFO_OUTLINE, ft.Column([
            key(dot(RISK["low"], 10), "Low risk"), key(dot(RISK["moderate"], 10), "Moderate risk"),
            key(dot(RISK["high"], 10), "High risk"), key(dot(RISK["extreme"], 10), "Extreme or burning"),
            key(dot(CONTAINED, 10), "Contained"), key(dot(HOTSPOT, 10), "NASA satellite hotspot"),
            key(ft.Icon(ft.Icons.LOCATION_ON, color=INFO_BLUE, size=14), "Citizen report"),
            key(ft.Icon(ft.Icons.CAMPAIGN, color=EMERGENCY, size=14), "Station notice"),
            key(dot(EMERGENCY, 10), "Projected spread (indicative)")], spacing=6, tight=True))
        self.zone_holder = ft.Container(content=app.zone_list, height=300)
        zones = panel("Zones by risk", ft.Icons.FORMAT_LIST_BULLETED, self.zone_holder)
        self.help = txt("Scroll, pinch or use + / - to zoom, drag to pan. Search any town, township or village, "
                        "or zoom in and tap the map for exact coordinates.", 11.5, FAINT)
        super().__init__([
            self.controls_row,
            ft.ResponsiveRow([
                ft.Container(col={"xs": 12, "lg": 9}, content=ft.Column([self.map_card, self.help], spacing=8)),
                ft.Container(col={"xs": 12, "lg": 3}, content=ft.Column([layers, legend, zones], spacing=14))],
                spacing=14, run_spacing=14, vertical_alignment=ft.CrossAxisAlignment.START)], spacing=14)

    def _toggle(self, key, value):
        self.map.layers[key] = bool(value)
        self.map._redraw()
        self.app.page.update()

    def _on_region(self, e):
        province = self.region.value
        if province == "all":
            self.map.reset_view()
        else:
            zs = [z for z in self.app.sim.zones if z["province"] == province]
            self.map.focus_on(sum(z["x"] for z in zs) / len(zs), sum(z["y"] for z in zs) / len(zs), 2.6)
        self.app.page.update()

    def _on_risk(self, e):
        v = self.risk.value
        levels = {"all": None, "high": {"high", "extreme"}, "moderate": {"moderate"}, "low": {"low"}}[v or "all"]
        self.map.risk_filter = levels
        self.app.zone_list.levels = levels
        self.app.zone_list.order = []
        self.map._redraw()
        self.app.refresh()

    def fit(self, mode, width):
        self.map_holder.height = 620 if mode == "desktop" else 520 if mode == "tablet" else max(340, min(460, int(width * 1.0)))
        self.zone_holder.height = 300
        self.controls_row.alignment = ft.MainAxisAlignment.END if mode != "phone" else ft.MainAxisAlignment.START
        self.region.width = self.risk.width = 190 if mode != "phone" else 150
        self.help.visible = True


# ---------------------------------------------------------------------------
# Alerts, reports, settings
# ---------------------------------------------------------------------------

FILTERS = [("all", "All", None), ("high", "High", ("extreme", "high")), ("info", "Info", ("info",)),
           ("resolved", "Resolved", ("contained",))]


class AlertsPage(ft.ResponsiveRow):
    def __init__(self, shell):
        self.app = app = shell.app
        self.filter = "all"
        self.state = None
        self.chips = ft.Row(spacing=8, wrap=True, run_spacing=8)
        self.listing = ft.Column(spacing=0, tight=True)
        body = ft.Column([self.chips, self.listing], spacing=8, tight=True)
        side = side_actions("Manage your alerts", ["Choose your town, how strong a fire to hear about and how far away."], [
            solid("Alert settings", ft.Icons.TUNE, need_login(app, lambda: screens.show_settings(app))),
            outline("Emergency contacts", ft.Icons.CONTACT_PHONE, need_login(app, lambda: screens.show_settings(app))),
            outline("Send me a test alert", ft.Icons.SEND, need_login(app, lambda: dialogs.show_profile(app))),
            outline("Incidents and timelines", ft.Icons.TIMELINE, lambda: screens.show_incidents(app)),
            outline("Station console", ft.Icons.LOCAL_FIRE_DEPARTMENT, lambda: screens.show_console(app)),
            txt("Smartwatches show alerts through the paired phone.", 11.5, FAINT)])
        super().__init__([
            ft.Container(col={"xs": 12, "lg": 8}, content=ft.Container(content=body, bgcolor=PANEL, border=ft.Border.all(1, LINE),
                                                                        border_radius=16, padding=18)),
            ft.Container(col={"xs": 12, "lg": 4}, content=side)], spacing=18, run_spacing=14,
            vertical_alignment=ft.CrossAxisAlignment.START)

    def _set(self, key):
        self.filter = key
        if self.state:
            self.render(self.state, None)
        self.app.page.update()

    def render(self, state, user):
        self.state = state
        feed = state["feed"]
        chips = []
        for key, label, classes in FILTERS:
            n = len(feed) if classes is None else sum(1 for e in feed if e["cls"] in classes)
            on = key == self.filter
            chips.append(ft.Container(
                content=txt(f"{label} ({n})", 12.5, "#FFFFFF" if on else TEXT, bold=on),
                bgcolor=INFO_BLUE if on else "#F1F4FA", border_radius=18, ink=True,
                padding=ft.Padding.symmetric(horizontal=14, vertical=7), on_click=lambda e, k=key: self._set(k)))
        self.chips.controls = chips
        classes = next(c for k, _, c in FILTERS if k == self.filter)
        rows = [e for e in feed if classes is None or e["cls"] in classes]
        self.listing.controls = [alert_row(e, (lambda ev: screens.show_incidents(self.app)) if e["cls"] in ("extreme", "high") else None,
                                           big=True) for e in rows] or [empty_note("Nothing in this list yet.")]


class ReportsPage(ft.Column):
    def __init__(self, shell):
        self.app = app = shell.app
        self.sig = None
        self.s_fires = StatCard(ft.Icons.LOCAL_FIRE_DEPARTMENT, "#E5484D", "#FDE7E7", "Active Fires")
        self.s_hot = StatCard(ft.Icons.SATELLITE_ALT, "#F59E0B", "#FEF1D6", "NASA Hotspots")
        self.s_rep = StatCard(ft.Icons.DESCRIPTION_OUTLINED, "#22A06B", "#DDF3E8", "Citizen Reports (24 h)")
        self.s_ver = StatCard(ft.Icons.VERIFIED_OUTLINED, "#3B82F6", "#E1ECFE", "Verified Reports")
        for tr in (app.tr_wind, app.tr_moist):
            tr.expand = False
        trends = panel("Environmental trends", ft.Icons.SHOW_CHART, ft.ResponsiveRow([
            ft.Container(col={"xs": 12, "md": 6}, content=app.tr_wind),
            ft.Container(col={"xs": 12, "md": 6}, content=app.tr_moist)], spacing=24, run_spacing=12))
        self.listing = ft.Column(spacing=0, tight=True)
        side = side_actions("Report smoke or fire", [
            "Drop a pin on the map. Reports are marked verified when a satellite hotspot is nearby or other people confirm them.",
            "A report does not alert fire crews. In an emergency use SOS or call 112."], [
            solid("Report now", ft.Icons.ADD_LOCATION_ALT, lambda: (shell.navigate("map"), app.start_report())),
            solid("Send SOS", ft.Icons.SOS, lambda: dialogs.show_emergency(app), EMERGENCY),
            outline("What to do now", ft.Icons.HEALTH_AND_SAFETY, app.open_safety),
            outline("Incidents and timelines", ft.Icons.TIMELINE, lambda: screens.show_incidents(app))])
        lower = ft.ResponsiveRow([
            ft.Container(col={"xs": 12, "lg": 8}, content=panel("Citizen reports, last 24 hours", ft.Icons.DESCRIPTION_OUTLINED, self.listing)),
            ft.Container(col={"xs": 12, "lg": 4}, content=side)], spacing=18, run_spacing=14,
            vertical_alignment=ft.CrossAxisAlignment.START)
        super().__init__([stat_row([self.s_fires, self.s_hot, self.s_rep, self.s_ver]), trends, lower], spacing=16)

    def render(self, state, user):
        rows = self.app.map.reports
        active = [f for f in state["fires"] if not f["contained"]]
        self.s_fires.set_delta(len(active))
        self.s_hot.set(len(self.app.map.hotspots), "From NASA FIRMS" if self.app.live else "Turn on Live NASA data", ft.Icons.REMOVE, DIM)
        verified = sum(1 for r in rows if r.get("verified", "unverified") != "unverified")
        self.s_rep.set(len(rows), "Reports need the server version" if config.IN_BROWSER else "Newest first", ft.Icons.REMOVE, DIM)
        self.s_ver.set(verified, "Satellite match or confirmed by others", ft.Icons.REMOVE, DIM)
        sig = tuple((r["id"], r.get("verified"), r.get("votes")) for r in rows)
        if sig == self.sig:
            return
        self.sig = sig
        out = []
        for r in rows[:30]:
            level = r.get("verified", "unverified")
            spot, km = places.nearest(r["lat"], r["lon"], 30)
            where = f"Near {spot['name']}, {spot['province']}" if spot else f'{r["lat"]:.3f}, {r["lon"]:.3f}'
            out.append(ft.Container(
                content=ft.Row([
                    ft.Icon(ft.Icons.VERIFIED if level != "unverified" else ft.Icons.HELP_OUTLINE, size=20,
                            color=RISK["low"] if level != "unverified" else FAINT),
                    ft.Column([txt(r["kind_label"], 13.5, TEXT, bold=True), txt(where, 12, DIM),
                               txt(reports.VERIFY_LABEL.get(level, ""), 11.5, FAINT)], spacing=2, expand=True),
                    txt(f'{r.get("votes", 0)} confirm', 11.5, DIM)], spacing=12),
                padding=ft.Padding.symmetric(vertical=11), ink=True, border=ft.Border.only(bottom=ft.BorderSide(1, LINE_SOFT)),
                on_click=lambda e, r=r: dialogs.show_report_detail(self.app, r)))
        self.listing.controls = out or [empty_note("No reports in the last 24 hours. Reports need the server version and a signed-in user.")]


TABS = [("profile", ft.Icons.PERSON_OUTLINE, "Profile"), ("alerts", ft.Icons.NOTIFICATIONS_NONE, "Notifications"),
        ("map", ft.Icons.MAP_OUTLINED, "Map Preferences"), ("privacy", ft.Icons.SHIELD_OUTLINED, "Data & Privacy"),
        ("system", ft.Icons.SETTINGS_OUTLINED, "System")]


class SettingsPage(ft.ResponsiveRow):
    def __init__(self, shell):
        self.shell = shell
        self.app = app = shell.app
        self.tab = "profile"
        self.user = None
        self.live_switch = ft.Switch(value=app.live, on_change=app.on_live_toggle, disabled=not firms.available())
        self.saver_switch = ft.Switch(value=app.saver, on_change=app.on_saver_toggle)
        self.tabs_col = ft.Column(spacing=4, tight=True)
        self.content = ft.Container(padding=22)
        left = ft.Container(content=self.tabs_col, bgcolor=PANEL, border=ft.Border.all(1, LINE), border_radius=16, padding=10)
        right = ft.Container(content=self.content, bgcolor=PANEL, border=ft.Border.all(1, LINE), border_radius=16)
        super().__init__([ft.Container(col={"xs": 12, "md": 4, "lg": 3}, content=left),
                          ft.Container(col={"xs": 12, "md": 8, "lg": 9}, content=right)],
                         spacing=18, run_spacing=14, vertical_alignment=ft.CrossAxisAlignment.START)
        self._draw()

    def set_tab(self, key):
        self.tab = key
        self._draw()
        self.app.page.update()

    def set_user(self, user):
        self.user = user
        self._draw()

    def sync(self):
        self.live_switch.value = self.app.live
        self.saver_switch.value = self.app.saver

    def _field(self, label, value):
        return ft.Column([txt(label, 12, DIM), ft.Container(content=txt(value or "-", 13.5, TEXT), bgcolor="#F7F9FC",
                          border=ft.Border.all(1, LINE), border_radius=8, padding=ft.Padding.symmetric(horizontal=12, vertical=10))],
                         spacing=4, tight=True)

    def _draw(self):
        app, go = self.app, self.shell.navigate
        self.tabs_col.controls = [ft.Container(
            content=ft.Row([ft.Icon(i, size=19, color=INFO_BLUE if k == self.tab else DIM),
                            txt(t, 13.5, INFO_BLUE if k == self.tab else TEXT, bold=k == self.tab)], spacing=12),
            bgcolor=SELECTED_BG if k == self.tab else None, border_radius=10, ink=True,
            padding=ft.Padding.symmetric(horizontal=14, vertical=12), on_click=lambda e, k=k: self.set_tab(k)) for k, i, t in TABS]
        user = self.user
        row = lambda sw, t, sub: ft.Row([sw, ft.Column([txt(t, 13.5, TEXT, bold=True), txt(sub, 12, DIM)], spacing=1, expand=True)],
                                        vertical_alignment=ft.CrossAxisAlignment.START)
        btns = lambda *b: ft.Row(list(b), spacing=10, wrap=True, run_spacing=8)
        if self.tab == "profile":
            if user:
                zone = next((z for z in app.sim.zones if z["id"] == user["home_zone_id"]), None)
                body = [txt("Profile", 18, TEXT, bold=True),
                        ft.Row([ft.Container(content=txt(initials(user["name"]), 22, "#FFFFFF", bold=True), width=64, height=64,
                                             border_radius=32, bgcolor="#8C7BFF", alignment=ft.Alignment.CENTER),
                                txt(user["name"], 16, TEXT, bold=True)], spacing=14),
                        self._field("Full name", user["name"]), self._field("Email address", user["email"]),
                        self._field("Mobile number", user.get("phone")),
                        self._field("Nearest town", f'{zone["name"].split(" (")[0]}, {zone["province"]}' if zone else ""),
                        btns(solid("Edit profile", ft.Icons.EDIT, lambda: dialogs.show_profile(app)),
                             outline("Log out", ft.Icons.LOGOUT, lambda: (app.set_user(None), app.toast("You have been logged out."))))]
            else:
                body = [txt("Profile", 18, TEXT, bold=True),
                        txt("Sign in to keep your town, alert choices and emergency contacts. You stay signed in on this device.", 13, DIM),
                        btns(solid("Log in", ft.Icons.LOGIN, lambda: dialogs.show_login(app)),
                             outline("Sign up", ft.Icons.PERSON_ADD, lambda: dialogs.show_signup(app)))]
        elif self.tab == "alerts":
            body = [txt("Notifications", 18, TEXT, bold=True),
                    txt("Fire alerts by SMS and email for your town: strength, distance, quiet hours and language "
                        "(English, Afrikaans, isiZulu, Setswana, Sesotho). Up to three emergency contacts get a text when you press SOS.", 13, DIM),
                    btns(solid("Alert settings", ft.Icons.TUNE, need_login(app, lambda: screens.show_settings(app))),
                         outline("Emergency contacts", ft.Icons.CONTACT_PHONE, need_login(app, lambda: screens.show_settings(app))),
                         outline("Send me a test alert", ft.Icons.SEND, need_login(app, lambda: dialogs.show_profile(app))))]
        elif self.tab == "map":
            body = [txt("Map Preferences", 18, TEXT, bold=True),
                    row(self.live_switch, "Live NASA data", "Real satellite detections (server version with a NASA key)."),
                    row(self.saver_switch, "Data saver", "Slower updates and a lighter map to save mobile data."),
                    txt("Choose which layers show on the map from the Map page.", 12, FAINT)]
        elif self.tab == "privacy":
            body = [txt("Data & Privacy", 18, TEXT, bold=True),
                    txt("Your alert location is stored rounded to about 5 km. Message logs keep no phone numbers or emails. "
                        "Your name and number are shared with fire stations only when you send an SOS and agreed to it.", 13, DIM),
                    txt("Fire detections come from NASA FIRMS, weather from Open-Meteo, place names from GeoNames and "
                        "hospitals from OpenStreetMap.", 13, DIM),
                    btns(outline("About and data sources", ft.Icons.INFO_OUTLINE, lambda: go("about")))]
        else:
            body = [txt("System", 18, TEXT, bold=True),
                    btns(outline("Public status", ft.Icons.PUBLIC, lambda: go("public")),
                         outline("All features", ft.Icons.APPS, lambda: go("features")),
                         outline("About and data", ft.Icons.INFO_OUTLINE, lambda: go("about")),
                         outline("What to do now", ft.Icons.HEALTH_AND_SAFETY, app.open_safety),
                         outline("Incidents and timelines", ft.Icons.TIMELINE, lambda: screens.show_incidents(app)),
                         outline("Station console", ft.Icons.LOCAL_FIRE_DEPARTMENT, lambda: screens.show_console(app)),
                         outline("Reset simulation", ft.Icons.REFRESH, app.reset))]
        self.content.content = ft.Column(body, spacing=14, tight=True)


# ---------------------------------------------------------------------------
# Feature cards
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Overview hub (Twilio-style cards)
# ---------------------------------------------------------------------------

def eyebrow(text):
    return txt(text.upper(), 11, DIM, bold=True)


def feature_item(icon, title, body, label, fn):
    """One feature: icon, title, one-line description and a link-style action."""
    return ft.Container(col={"xs": 12, "md": 6}, padding=ft.Padding.only(bottom=6), content=ft.Column([
        ft.Row([ft.Icon(icon, color=INFO_BLUE, size=18), txt(title, 14, TEXT, bold=True)], spacing=8, tight=True),
        txt(body, 12.5, DIM),
        ft.TextButton(label, icon=ft.Icons.ARROW_FORWARD, on_click=lambda e: fn(),
                      style=ft.ButtonStyle(padding=ft.Padding.symmetric(horizontal=0, vertical=2))),
    ], spacing=3, tight=True))


def section_card(kicker, headline, intro, items, side=None):
    """Large rounded card: eyebrow, headline, two-column feature list, optional right panel."""
    head = txt(headline, 26, TEXT, bold=True)
    left = ft.Column([eyebrow(kicker), head, txt(intro, 13.5, DIM),
                      ft.Container(height=6),
                      ft.ResponsiveRow([feature_item(*i) for i in items], spacing=18, run_spacing=6)],
                     spacing=6, tight=True)
    cols = [ft.Container(content=left, col={"xs": 12, "lg": 8 if side else 12})]
    if side is not None:
        cols.append(ft.Container(content=side, col={"xs": 12, "lg": 4}))
    box = ft.Container(
        content=ft.ResponsiveRow(cols, spacing=24, run_spacing=16, vertical_alignment=ft.CrossAxisAlignment.START),
        bgcolor=PANEL, border=ft.Border.all(1, LINE), border_radius=18,
        padding=ft.Padding.symmetric(horizontal=26, vertical=24),
        shadow=ft.BoxShadow(blur_radius=18, color="#0F2F6FED", offset=ft.Offset(0, 4)))
    box.headline = head
    return box


def side_panel(title, lines, buttons):
    """Right-hand 'try it' panel, like the SMS tester in the Twilio overview."""
    return ft.Container(
        content=ft.Column([txt(title, 15, TEXT, bold=True), *[txt(t, 12.5, DIM) for t in lines], *buttons], spacing=10, tight=True),
        bgcolor="#F4F7FE", border=ft.Border.all(1, LINE), border_radius=14, padding=18)



class FeaturesPage(ft.Column):
    """Every feature, grouped into section cards."""

    def __init__(self, shell):
        app = shell.app
        go = shell.navigate
        nl = lambda fn: need_login(app, fn)
        monitor = section_card(
            "Live monitoring", "See what is burning, and what could burn next",
            "Satellite detections, sensor towns, citizen reports and station notices on one map of South Africa.",
            [(ft.Icons.MAP, "Live fire map", "Zoomable map with place search and exact coordinates for any town, township or village.",
              "Open the map", lambda: go("map")),
             (ft.Icons.SATELLITE_ALT, "NASA satellite hotspots", "Real detections from NASA VIIRS, refreshed about every 15 minutes (server version).",
              "See hotspots", lambda: go("map")),
             (ft.Icons.TRENDING_UP, "Fire-spread projection", "Where an active fire could reach in 3 hours from wind, fuel moisture and slope. Indicative only.",
              "Show active fires", lambda: (go("map"), app.map.focus_fires())),
             (ft.Icons.TIMELINE, "Incidents and timelines", "Each fire's history: first detection, growth, alerts sent, status.",
              "View incidents", lambda: screens.show_incidents(app)),
             (ft.Icons.PUBLIC, "Public status page", "Plain-language regional status and the zones under advisory.",
              "Open status", lambda: go("public")),
             (ft.Icons.DATA_SAVER_ON, "Data saver", "Slower updates and a lighter map for low data. Turn it on in Settings.",
              "Go to the switch", lambda: go("settings"))],
            side=side_panel("Report smoke or fire", ["Drop a pin on the map. Reports are marked verified when a satellite "
                                                     "hotspot is nearby or other people confirm them."],
                            [ft.FilledButton("Report now", icon=ft.Icons.ADD_LOCATION_ALT, on_click=lambda e: (go("map"), app.start_report()),
                                             style=ft.ButtonStyle(bgcolor=INFO_BLUE, color="#FFFFFF"))]))

        respond = section_card(
            "Emergency response", "Get help to people quickly",
            "Alert fire stations with your location, and know what to do while you wait.",
            [(ft.Icons.SOS, "SOS to fire stations", "Sends your location and number to verified stations and shows what was and was not delivered.",
              "Send SOS", lambda: dialogs.show_emergency(app)),
             (ft.Icons.HEALTH_AND_SAFETY, "What to do now", "Checklists for veld, house and informal-settlement fires, plus nearby hospitals and assembly points.",
              "Open checklist", app.open_safety),
             (ft.Icons.LOCAL_FIRE_DEPARTMENT, "Station console", "For stations and Fire Protection Associations: acknowledge and dispatch SOS, post notices.",
              "Open console", lambda: screens.show_console(app)),
             (ft.Icons.CAMPAIGN, "Station and FPA notices", "Verified status, evacuation warnings and extrication requests appear on the map.",
              "See incidents", lambda: screens.show_incidents(app))],
            side=side_panel("In an emergency", ["Call first. Firewatch supports emergency services; it does not replace them."],
                            [ft.FilledButton("Send SOS", icon=ft.Icons.SOS, on_click=lambda e: dialogs.show_emergency(app),
                                             style=ft.ButtonStyle(bgcolor=EMERGENCY, color="#FFFFFF")),
                             ft.OutlinedButton("Call 112", icon=ft.Icons.CALL, on_click=lambda e: open_url(app.page, "tel:112"))]))

        account = section_card(
            "Alerts and account", "Hear about fires near you, in your language",
            "Pick your place, how strong a fire to hear about and how far away.",
            [(ft.Icons.NOTIFICATIONS_ACTIVE, "Fire alerts by SMS and email", "Set your exact town or village and how you want to be told.",
              "Set up alerts", lambda: (screens.show_settings(app) if app.user else dialogs.show_signup(app))),
             (ft.Icons.TUNE, "Alert settings", "Strength, distance, quiet hours and language: English, Afrikaans, isiZulu, Setswana, Sesotho.",
              "Open settings", nl(lambda: screens.show_settings(app))),
             (ft.Icons.CONTACT_PHONE, "Emergency contacts", "Up to three people get a text when you press SOS.",
              "Add contacts", nl(lambda: screens.show_settings(app))),
             (ft.Icons.PERSON, "Your profile", "Name, number, town and exact place. You stay signed in on this device.",
              "Open profile", nl(lambda: dialogs.show_profile(app)))],
            side=side_panel("Send a test alert", ["Check that alerts reach your phone (server version). Smartwatches show them "
                                                  "through the paired phone."],
                            [ft.FilledButton("Open my profile", icon=ft.Icons.SEND, on_click=lambda e: nl(lambda: dialogs.show_profile(app))(),
                                             style=ft.ButtonStyle(bgcolor=INFO_BLUE, color="#FFFFFF"))]))

        trust = section_card(
            "Trust and data", "Honest about where the data comes from",
            "What each source gives you, and what Firewatch cannot do.",
            [(ft.Icons.WATCH, "Phone, tablet, desktop and watch", "The layout adapts to the screen. A very small screen gets a glance view with status, SOS and Call 112.",
              "Read more", lambda: go("about")),
             (ft.Icons.PRIVACY_TIP, "Privacy", "Subscriber locations are stored rounded to about 5 km. Message logs hold no phone numbers or emails.",
              "Read more", lambda: go("about")),
             (ft.Icons.INFO_OUTLINE, "About and data sources", "Where each piece of data comes from, emergency numbers and limits.",
              "Read more", lambda: go("about"))])

        self.cards = [monitor, respond, account, trust]
        self.headlines = [c.headline for c in self.cards]
        super().__init__(self.cards, spacing=18)

    def set_compact(self, compact):
        for h in self.headlines:
            h.size = 20 if compact else 26
        for c in self.cards:
            c.padding = ft.Padding.symmetric(horizontal=16 if compact else 26, vertical=16 if compact else 24)


def build_about(shell):
    app = shell.app

    def number(label, num):
        return ft.Row([txt(label, 13, TEXT), ft.Container(expand=True),
                       ft.TextButton(num, icon=ft.Icons.CALL, on_click=lambda e: open_url(app.page, "tel:" + num))])

    sources = [
        ("Fire detections", "NASA FIRMS (VIIRS satellites), free, about 3 hours behind real time."),
        ("Weather for spread", "Open-Meteo forecast for active fires. Zone cards and trend charts still use simulated weather."),
        ("Place names", "GeoNames (CC BY 4.0). Community data: some rural places may be missing or slightly off."),
        ("Hospitals and assembly points", "OpenStreetMap volunteers. Incomplete in rural areas: confirm locally."),
        ("Reports, alerts, incidents", "Stored in your Supabase database; SMS through Twilio, BulkSMS or Clickatell; email through SMTP."),
    ]
    limits = [
        "Satellite data cannot confirm that a fire is out. Only ground crews can.",
        "The spread arrow is an indicative model, not an operational forecast.",
        "SMS 'sent' means the provider accepted it, not that a person read it.",
        "Only stations marked verified in stations.json are messaged. Otherwise call 112.",
        "Firewatch supports emergency services; it does not replace them.",
    ]
    return ft.Column([
        ft.ResponsiveRow([
            ft.Container(col={"xs": 12, "lg": 6}, content=card(ft.Column(
                [txt("Emergency numbers", 15, TEXT, bold=True),
                 number("From any cell phone", "112"), number("Police (SAPS)", "10111"), number("Ambulance", "10177"),
                 txt("For a fire, call 112 or your local municipal fire service.", 12, DIM)], spacing=6), padding=16)),
            ft.Container(col={"xs": 12, "lg": 6}, content=card(ft.Column(
                [txt("Devices", 15, TEXT, bold=True),
                 txt("Desktop: full menu and three-column console. Tablet: slim menu. Phone: bottom navigation "
                     "and a floating SOS button. Very small screens (smart-watch size): a glance view with status, "
                     "the nearest fire, SOS and Call 112.", 12.5, DIM),
                 txt("Flet apps cannot be installed on Apple Watch or Wear OS. SMS, email and Telegram alerts reach a "
                     "watch through its paired phone.", 12.5, DIM),
                 ft.Row([ft.OutlinedButton("Reset simulation", icon=ft.Icons.REFRESH, on_click=app.reset)])], spacing=8),
                padding=16)),
        ], spacing=14, run_spacing=14),
        card(ft.Column([txt("Where the data comes from", 15, TEXT, bold=True)] + [
            ft.Row([ft.Container(content=txt(a, 12.5, TEXT, bold=True), width=190), ft.Container(content=txt(b, 12.5, DIM), expand=True)],
                   vertical_alignment=ft.CrossAxisAlignment.START, wrap=True) for a, b in sources], spacing=8), padding=16),
        card(ft.Column([txt("Limits you should know about", 15, TEXT, bold=True)] + [
            ft.Row([ft.Icon(ft.Icons.INFO_OUTLINE, size=16, color=DIM), ft.Container(content=txt(t, 12.5, DIM), expand=True)],
                   vertical_alignment=ft.CrossAxisAlignment.START, spacing=8) for t in limits], spacing=8), padding=16),
    ], spacing=14)


class WatchView(ft.Container):
    """Glance view for tiny screens: status, nearest fire, SOS, call 112."""

    def __init__(self, app):
        self.app = app
        self.ring = ft.Container(width=80, height=80, border_radius=40, bgcolor=RISK["low"], alignment=ft.Alignment.CENTER)
        self.count = txt("0", 34, "#FFFFFF", bold=True)
        self.ring.content = self.count
        self.line1 = txt("No fires", 15, TEXT, bold=True)
        self.line2 = txt("", 11.5, DIM)
        self.sos = ft.Container(
            content=txt("SOS", 20, "#FFFFFF", bold=True), width=72, height=72, border_radius=36, bgcolor=EMERGENCY,
            alignment=ft.Alignment.CENTER, shadow=ft.BoxShadow(blur_radius=8, color="#55000000"),
            on_click=lambda e: dialogs.show_emergency(app))
        self.call = ft.TextButton("Call 112", icon=ft.Icons.CALL, on_click=lambda e: open_url(app.page, "tel:112"),
                                  style=ft.ButtonStyle(color=EMERGENCY))
        super().__init__(
            content=ft.Column([self.ring, self.line1, self.line2, self.sos, self.call], spacing=6,
                              horizontal_alignment=ft.CrossAxisAlignment.CENTER, scroll=ft.ScrollMode.AUTO),
            alignment=ft.Alignment.CENTER, expand=True, padding=10, bgcolor=BG)

    def fit(self, height):
        """Shrink the pieces on very short screens (round watch faces are about 200 px tall)."""
        small = bool(height) and height < 260
        size = 52 if small else 80
        self.ring.width = self.ring.height = size
        self.ring.border_radius = size // 2
        self.count.size = 24 if small else 34
        sos = 56 if small else 72
        self.sos.width = self.sos.height = sos
        self.sos.border_radius = sos // 2
        self.line2.visible = not small
        self.line1.size = 13 if small else 15

    def render(self, state, user):
        from stations import distance_km
        active = [f for f in state["fires"] if not f["contained"]]
        zones = state["zones"]
        home = next((z for z in zones if user and z["id"] == user["home_zone_id"]), None)
        ref = home or max(zones, key=lambda z: z["risk"])
        worst = "extreme" if any(f["severity"] == "extreme" for f in active) else ("high" if active else ref["risk_level"])
        self.ring.bgcolor = RISK.get(worst, RISK["low"])
        self.count.value = str(len(active))
        self.line1.value = f'{len(active)} active fire{"s" if len(active) != 1 else ""}' if active else "No active fires"
        if active:
            def km(f):
                z = next((z for z in zones if z["id"] == f["zone_id"]), None)
                return distance_km(ref["lat"], ref["lon"], z["lat"], z["lon"]) if z else 9999
            nearest = min(active, key=km)
            self.line2.value = f'Nearest: {nearest["zone_name"].split(" (")[0]}, {km(nearest):.0f} km from {ref["name"].split(" (")[0]}'
        else:
            self.line2.value = f'{ref["name"].split(" (")[0]}: {ref["risk_level"]} danger'




# ---------------------------------------------------------------------------
# The shell
# ---------------------------------------------------------------------------

PAGES = {
    "overview": ("Overview", ""),
    "map": ("Map", "Real-time wildfire locations, risk zones and monitoring data."),
    "alerts": ("Alerts", "Live and recent wildfire alerts from across the region."),
    "reports": ("Reports", "Detections, citizen reports and environmental trends."),
    "public": ("Public status", "What the public should know right now."),
    "settings": ("Settings", "Manage your account, notifications and application preferences."),
    "features": ("All features", "Everything Firewatch can do, in one place."),
    "about": ("About and data", "Data sources, emergency numbers, devices and limits."),
}


class Shell(ft.Container):
    def __init__(self, app):
        self.app = app
        self.mode = None
        self.current = "overview"
        self.dash = Dashboard(self)
        self.alerts_page = AlertsPage(self)
        self.reports_page = ReportsPage(self)
        self.settings_page = SettingsPage(self)
        self.features = FeaturesPage(self)
        self.map_page = MapPage(self)
        self.pages = {"overview": self.dash, "map": self.map_page, "alerts": self.alerts_page, "reports": self.reports_page,
                      "public": app.public, "settings": self.settings_page, "features": self.features,
                      "about": build_about(self)}
        self.title = txt("", 26, TEXT, bold=True)
        self.desc = txt("", 13, DIM)
        self.title_box = ft.Container(content=ft.Column([self.title, self.desc], spacing=4, tight=True),
                                      padding=ft.Padding.only(left=24, right=24, top=18, bottom=2))
        self.holder = ft.Container(content=self.dash, padding=ft.Padding.symmetric(horizontal=24, vertical=14))
        self.footer_box = ft.Container(content=app.footer, alignment=ft.Alignment.CENTER,
                                       padding=ft.Padding.only(top=4, bottom=96, left=16, right=16))
        self.scroller = ft.Column([self.title_box, self.holder, self.footer_box], scroll=ft.ScrollMode.AUTO, expand=True, spacing=0)
        self.sidebar = Sidebar(self)
        self.bottom_bar = BottomBar(self)
        self.watch = WatchView(app)
        self.scene = ft.Container(content=self.scroller, expand=True, image=backdrop())
        self.main = ft.Column([app.header, self.scene], spacing=0, expand=True)
        self.body = ft.Row([self.sidebar, self.main], spacing=0, expand=True, vertical_alignment=ft.CrossAxisAlignment.STRETCH)
        self.root = ft.Column([self.body, self.bottom_bar], spacing=0, expand=True)
        super().__init__(content=self.root, expand=True, bgcolor=PAGE_BG)
        self.navigate("overview", update=False)

    # -- navigation ------------------------------------------------------------
    def navigate(self, key, update=True):
        if key not in PAGES:
            return
        self.current = key
        title, desc = PAGES[key]
        self.title.value, self.desc.value = title, desc
        self.title_box.visible = key != "overview"
        self.holder.content = self.pages[key]
        self.app.showing_public = key == "public"
        self.sidebar.select(key)
        self.bottom_bar.select(key)
        if update:
            self.scroller.scroll_to(offset=0, duration=0)
            self.app.refresh()

    # -- layout ---------------------------------------------------------------
    def apply(self, mode, width=None):
        if mode == "watch":
            self.watch.fit(self.app.page.height)
        if mode == self.mode:
            return
        self.mode = mode
        app = self.app
        if mode == "watch":
            self.root.controls = [self.watch]
            app.sos.visible = False
        else:
            self.root.controls = [self.body, self.bottom_bar]
            app.sos.visible = True
            phone = mode == "phone"
            self.sidebar.visible = not phone
            self.sidebar.set_compact(mode == "tablet")
            self.bottom_bar.visible = phone
            pad = 12 if phone else 24
            self.title_box.padding = ft.Padding.only(left=pad, right=pad, top=12 if phone else 18, bottom=2)
            self.holder.padding = ft.Padding.symmetric(horizontal=8 if phone else pad, vertical=8 if phone else 14)
            self.title.size = 20 if phone else 26
            self.desc.visible = not phone
            self.dash.set_compact(phone or mode == "tablet")
            self.features.set_compact(phone or mode == "tablet")
            app.sos.bottom = 76 if phone else 84
        app.header.apply_mode(mode)

    def fit(self, mode, width):
        self.map_page.fit(mode, width)

    def set_user(self, user):
        self.app.header.set_user(user)
        self.settings_page.set_user(user)

    def update_state(self, state, user):
        app = self.app
        active = [f for f in state["fires"] if not f["contained"]]
        app.header.set_live(app.live)
        app.header.set_alert(active)
        self.sidebar.set_alerts(len(active))
        self.settings_page.sync()
        self.map_page.live_chip.content.value = "Live view" if app.live else "Simulation"
        cur = self.current
        if self.mode == "watch":
            self.watch.render(state, user)
        elif cur == "overview":
            self.dash.render(state, user)
        elif cur == "alerts":
            self.alerts_page.render(state, user)
        elif cur == "reports":
            self.reports_page.render(state, user)
