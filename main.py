"""
Firewatch: wildfire early-warning console (Flet, pure Python).

Modules
  simulation.py  the engine (no UI)
  geo.py         South Africa outline and projection
  stations.py    fire stations + nearest-station search
  auth.py        sign up / log in storage
  firemap.py     interactive zoomable map
  dialogs.py     sign up, log in, profile and emergency dialogs
  ui.py          theme colours and small helpers

Run:
    pip install -r requirements.txt
    python main.py
"""

import asyncio
import os
import sys
from datetime import datetime

import flet as ft

import alerts  # noqa: F401  (used by dialogs)
import auth
import config
import dialogs
import firms
import incidents
import monitor
import places
import reports
import screens
from firemap import FireMap
from simulation import MAX_HISTORY, TICK_SECONDS, Simulation
from ui import (
    CONTAINED, DIM, EMERGENCY, FAINT, FEED_COLOR, INFO_BLUE,
    LINE, LINE_SOFT, MOIST, PANEL, RISK, TEXT, WIND, BG, card, chip, compass_dir,
    dot, txt, HOTSPOT,
)


# ---------------------------------------------------------------------------
# Reusable UI components
# ---------------------------------------------------------------------------

class StatTile(ft.Container):
    def __init__(self, label, sub="", value_size=24):
        self.value = txt("—", value_size, TEXT, font_family="monospace")
        self.sub = txt(sub, 11, DIM)
        super().__init__(
            content=ft.Column(
                [
                    txt(label, 12, FAINT),
                    self.value,
                    self.sub,
                ],
                spacing=3,
                tight=True,
            ),
            padding=ft.Padding.symmetric(vertical=4),
        )

    def set(self, value, sub=None, color=TEXT):
        self.value.value = str(value)
        self.value.color = color
        if sub is not None:
            self.sub.value = sub


class RiskBar(ft.Container):
    def __init__(self):
        self.bar = ft.ProgressBar(value=0, color=RISK["low"], bgcolor=LINE_SOFT, height=4)
        super().__init__(content=self.bar, padding=0)

    def set(self, fraction, color):
        self.bar.value = max(0, min(1, fraction))
        self.bar.color = color


class ZoneRow(ft.Container):
    def __init__(self):
        self.name = txt("", 13, TEXT, bold=False)
        self.flag = txt("", 11, RISK["extreme"])
        self.meta = txt("", 11, DIM)
        self.bar = RiskBar()

        super().__init__(
            content=ft.Column(
                [
                    ft.Row([self.name, self.flag], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    self.meta,
                    self.bar,
                ],
                spacing=3,
            ),
            padding=ft.Padding.symmetric(vertical=8),
            border=ft.Border.only(bottom=ft.BorderSide(1, LINE_SOFT)),
        )

    def render(self, zone, wind_speed):
        self.name.value = zone["name"]
        self.flag.value = "Burning" if zone["on_fire"] else ""
        self.meta.value = (
            f'{zone["province"]} · {round(zone["temp"])}°F, '
            f'{round(zone["moisture"])}% moisture, wind {round(wind_speed)} km/h'
        )
        self.bar.set(zone["risk"], RISK[zone["risk_level"]])


class ZoneList(ft.ListView):
    def __init__(self):
        super().__init__(expand=True, spacing=0, auto_scroll=False)
        self.rows = {}
        self.order = []
        self.limit = 30          # only the riskiest zones are drawn (fewer widgets = faster)

    def render(self, zones, wind_speed):
        ranked = sorted(zones, key=lambda z: -z["risk"])[: self.limit]
        ids = [z["id"] for z in ranked]

        if ids != self.order:
            self.controls = []
            for zone in ranked:
                row = self.rows.setdefault(zone["id"], ZoneRow())
                self.controls.append(row)
            self.order = ids

        for zone in ranked:
            self.rows[zone["id"]].render(zone, wind_speed)


class FeedItem(ft.Container):
    def __init__(self, entry):
        color = FEED_COLOR.get(entry["cls"], DIM)
        top = txt(f'{entry["ts"]}   {entry["tag"]}', 11, color)
        body = txt(entry["text"].replace("[b]", "").replace("[/b]", ""), 12.5, TEXT)
        body.color = TEXT
        super().__init__(
            content=ft.Column([top, body], spacing=2, tight=True),
            padding=ft.Padding.symmetric(vertical=9),
            border=ft.Border.only(bottom=ft.BorderSide(1, LINE_SOFT)),
        )


class FeedList(ft.ListView):
    def __init__(self):
        super().__init__(expand=True, spacing=0, auto_scroll=False)
        self.signature = None

    def render(self, feed):
        sig = tuple((e["ts"], e["tag"], e["text"]) for e in feed)
        if sig == self.signature:
            return
        self.signature = sig
        self.controls = [FeedItem(e) for e in feed]


class Trend(ft.Container):
    def __init__(self, title, color, lo, hi):
        self.title = txt(title, 12, DIM)
        self.value = txt("—", 14, TEXT, font_family="monospace")
        self.color = color
        self.lo = lo
        self.hi = hi
        self.bars = ft.Row(spacing=2, vertical_alignment=ft.CrossAxisAlignment.END)
        super().__init__(
            content=ft.Column(
                [
                    ft.Row(
                        [self.title, ft.Container(expand=True), self.value],
                        tight=True,
                    ),
                    ft.Container(content=self.bars, height=65),
                ],
                spacing=6,
            ),
            expand=True,
        )

    def set_data(self, data):
        values = list(data)[-30:]
        if not values:
            return
        self.bars.controls = []
        span = max(self.hi - self.lo, 1)
        for value in values:
            frac = max(0.08, min(1, (value - self.lo) / span))
            self.bars.controls.append(
                ft.Container(
                    width=7,
                    height=round(55 * frac),
                    bgcolor=self.color,
                    border_radius=2,
                )
            )


class StatusPill(ft.Container):
    def __init__(self):
        self.dot_control = dot(RISK["low"], 7)
        self.label = txt("Connecting…", 12, TEXT)
        super().__init__(
            content=ft.Row(
                [self.dot_control, self.label],
                spacing=8,
                tight=True,
            ),
            border=ft.Border.all(1, LINE),
            border_radius=15,
            bgcolor=PANEL,
            padding=ft.Padding.symmetric(horizontal=12, vertical=6),
        )

    def set_state(self, alert, label):
        self.label.value = label
        self.dot_control.bgcolor = RISK["extreme"] if alert else RISK["low"]
        self.label.color = RISK["extreme"] if alert else TEXT
        self.border = ft.Border.all(1, RISK["extreme"] if alert else LINE)



def initials(name):
    parts = [p for p in name.split() if p]
    return (parts[0][0] + (parts[-1][0] if len(parts) > 1 else "")).upper() if parts else "?"


class Header(ft.Container):
    def __init__(self, app):
        self.app = app
        self.clock = txt("--:--:--", 12, DIM, font_family="monospace")
        self.pill = StatusPill()
        self.toggle_button = ft.OutlinedButton("Public view", on_click=app.toggle_view)
        self.reset_button = ft.OutlinedButton("Reset", on_click=app.reset)
        self.mobile = False
        # Three-line menu: Log in / Sign up (or profile / log out once signed in).
        self.menu = ft.PopupMenuButton(icon=ft.Icons.MENU, icon_size=24, tooltip="Menu", items=[])
        self.buttons = ft.Row(alignment=ft.MainAxisAlignment.END, wrap=True)

        super().__init__(
            content=ft.ResponsiveRow(
                [
                    ft.Container(
                        col={"xs": 12, "md": 5},
                        content=ft.Column(
                            [
                                ft.Row(
                                    [
                                        dot(TEXT, 9),
                                        txt("Firewatch", 19, TEXT, bold=True),
                                    ],
                                    spacing=8,
                                    tight=True,
                                ),
                                txt(
                                    "Live sensor fusion and fire-spread projection, "
                                    "South Africa",
                                    12,
                                    DIM,
                                ),
                            ],
                            spacing=2,
                            tight=True,
                        ),
                    ),
                    ft.Container(col={"xs": 12, "md": 7}, content=self.buttons),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            bgcolor=PANEL,
            padding=ft.Padding.symmetric(horizontal=16, vertical=10),
            border=ft.Border.only(bottom=ft.BorderSide(1, LINE)),
        )
        self.set_user(None)

    def set_user(self, user):
        app = self.app
        items = []
        if self.mobile:
            # On a phone the extra buttons live in the menu so the header stays one line.
            items += [
                ft.PopupMenuItem(content="Console view" if app.showing_public else "Public view",
                                 icon=ft.Icons.PUBLIC, on_click=app.toggle_view),
                ft.PopupMenuItem(content="Reset simulation", icon=ft.Icons.REFRESH,
                                 on_click=app.reset),
            ]
        items += [
            ft.PopupMenuItem(content="Incidents and timelines", icon=ft.Icons.TIMELINE,
                             on_click=lambda e: screens.show_incidents(app)),
            ft.PopupMenuItem(content="What to do now", icon=ft.Icons.HEALTH_AND_SAFETY,
                             on_click=lambda e: app.open_safety()),
            ft.PopupMenuItem(content="Station console", icon=ft.Icons.LOCAL_FIRE_DEPARTMENT,
                             on_click=lambda e: screens.show_console(app)),
        ]
        if user is None:
            items += [
                ft.PopupMenuItem(content="Log in", icon=ft.Icons.LOGIN,
                                 on_click=lambda e: dialogs.show_login(app)),
                ft.PopupMenuItem(content="Sign up", icon=ft.Icons.PERSON_ADD,
                                 on_click=lambda e: dialogs.show_signup(app)),
            ]
        else:
            items += [
                ft.PopupMenuItem(content=f"Signed in as {user['name'].split()[0]}",
                                 icon=ft.Icons.ACCOUNT_CIRCLE, disabled=True),
                ft.PopupMenuItem(content="My profile", icon=ft.Icons.PERSON,
                                 on_click=lambda e: dialogs.show_profile(app)),
                ft.PopupMenuItem(content="Alert settings and contacts", icon=ft.Icons.TUNE,
                                 on_click=lambda e: screens.show_settings(app)),
                ft.PopupMenuItem(content="Log out", icon=ft.Icons.LOGOUT,
                                 on_click=lambda e: (app.set_user(None), app.toast("You have been logged out."))),
            ]
        self.menu.items = items
        if self.mobile:
            self.buttons.controls = [self.pill, self.menu]
        else:
            self.buttons.controls = [
                self.clock, self.pill, self.reset_button, self.toggle_button, self.menu,
            ]


# ---------------------------------------------------------------------------
# Public view
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Public view
# ---------------------------------------------------------------------------

class PublicView(ft.Column):
    def __init__(self):
        self.banner = ft.Container()
        self.mine = ft.Container()
        self.advisories = ft.Column(spacing=0)
        super().__init__(
            [self.banner, self.mine, card(self.advisories, padding=0)],
            spacing=14,
        )

    def render_mine(self, state, user):
        """A 'your area' card for the signed-in user."""
        if not user:
            self.mine.content = card(
                ft.Row([ft.Icon(ft.Icons.INFO_OUTLINE, color=INFO_BLUE, size=20),
                        txt("Sign up to see alerts for your own town and to send emergency "
                            "alerts with your details attached.", 13, DIM)], spacing=10),
                padding=14)
            return
        zone = next((z for z in state["zones"] if z["id"] == user["home_zone_id"]), None)
        if not zone:
            return
        burning = zone["on_fire"]
        level = "extreme" if burning else zone["risk_level"]
        msg = ("Fire detected in your area. Follow instructions from emergency services."
               if burning else f"Fire danger is {zone['risk_level']} in your area right now.")
        self.mine.content = card(
            ft.Row([ft.Icon(ft.Icons.LOCATION_ON, color=RISK[level], size=22),
                    ft.Column([txt(f"Your area: {zone['name'].split(' (')[0]}, {zone['province']}", 14, TEXT, bold=True),
                               txt(msg, 12.5, DIM)], spacing=2, expand=True),
                    chip(level, RISK[level])], spacing=10),
            padding=14)

    def render(self, state, user=None):
        self.render_mine(state, user)
        active = [f for f in state["fires"] if not f["contained"]]
        extreme = [f for f in active if f["severity"] == "extreme"]

        if extreme:
            title = "Evacuation advisory in effect"
            body = (
                f"Active fire detections with rapid spread potential are affecting "
                f"{len(extreme)} zone(s). Follow instructions from local emergency "
                "services and be ready to leave immediately if directed."
            )
            color = RISK["extreme"]
        elif active:
            title = "Active fire activity nearby"
            body = (
                f"Fire crews are responding to {len(active)} detection(s) in the region. "
                "Monitor conditions and prepare an evacuation kit."
            )
            color = RISK["high"]
        else:
            hot = [z for z in state["zones"] if z["risk_level"] in ("high", "extreme")]
            if hot:
                title = "Elevated fire danger"
                body = (
                    f"Wind, low fuel moisture and temperature are raising fire risk in "
                    f"{len(hot)} zone(s). No active fires detected at this time."
                )
                color = RISK["moderate"]
            else:
                title = "No active fire danger reported"
                body = (
                    "The sensor network reports normal conditions region-wide. "
                    "This page updates automatically as conditions change."
                )
                color = RISK["low"]

        self.banner.content = ft.Container(
            content=ft.Column(
                [
                    txt("Regional fire status", 12.5, DIM),
                    txt(title, 24, TEXT, bold=True),
                    txt(body, 14, DIM),
                ],
                spacing=6,
            ),
            border=ft.Border(
                left=ft.BorderSide(4, color),
                top=ft.BorderSide(1, LINE),
                right=ft.BorderSide(1, LINE),
                bottom=ft.BorderSide(1, LINE),
            ),
            padding=ft.Padding.symmetric(horizontal=24, vertical=20),
            bgcolor=PANEL,
            border_radius=8,
        )

        rows = [
            ft.Container(
                content=txt("Zones with active advisories", 14, TEXT, bold=True),
                padding=ft.Padding.symmetric(horizontal=14, vertical=11),
                border=ft.Border.only(bottom=ft.BorderSide(1, LINE_SOFT)),
            )
        ]
        if active:
            for fire in active:
                rows.append(
                    ft.Container(
                        content=ft.Row(
                            [
                                txt(f'{fire["zone_name"]}, {fire["province"]}', 14, TEXT),
                                chip(fire["severity"], RISK[fire["severity"]]),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                        padding=ft.Padding.symmetric(horizontal=14, vertical=11),
                        border=ft.Border.only(bottom=ft.BorderSide(1, LINE_SOFT)),
                    )
                )
        else:
            rows.append(
                ft.Container(
                    content=txt("No zones are currently under advisory.", 13.5, DIM),
                    padding=14,
                )
            )

        self.advisories.controls = rows



# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

class FirewatchApp:
    def __init__(self, page: ft.Page, saver=False, prefs=None):
        self.page = page
        self.prefs = prefs
        self.saver = saver
        self.live = firms.available()          # real NASA data by default when a key is set
        self._live_key = None
        self._seen_hotspots = set()
        self._tick_n = 0
        self.sim = Simulation()
        if self.live:
            self.sim.set_live(True)
        self.showing_public = False
        self.running = True
        page.on_close = self.stop

        page.title = "Firewatch — Live Detection Console"
        page.bgcolor = BG
        page.padding = 0
        page.theme_mode = ft.ThemeMode.LIGHT
        page.scroll = ft.ScrollMode.AUTO
        page.horizontal_alignment = ft.CrossAxisAlignment.STRETCH

        self.user = None
        self.station = None          # set after a station logs in to the console
        self.keep_signed_in = True   # remember the signed-in person in this browser
        self.mobile = False
        self._layout_key = None
        self.header = Header(self)
        self.ops = self.build_ops()
        self.public = PublicView()

        self.holder = ft.Container(content=self.ops, padding=16)
        self.footer = txt("", 11, FAINT)

        page.add(
            self.header,
            self.holder,
            ft.Container(
                content=self.footer,
                alignment=ft.Alignment.CENTER,
                padding=ft.Padding.only(top=4, bottom=100),
            ),
        )

        # Round SOS button: floats at the bottom-right, above the page content,
        # and sits clear of the page footer.
        self.sos = ft.Container(
            content=ft.Column(
                [ft.Icon(ft.Icons.WARNING_AMBER, color="#FFFFFF", size=26),
                 txt("SOS", 11, "#FFFFFF", bold=True)],
                spacing=0, tight=True,
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            width=66, height=66, border_radius=33, bgcolor=EMERGENCY,
            alignment=ft.Alignment.CENTER, tooltip="Emergency alert",
            shadow=ft.BoxShadow(blur_radius=10, color="#55000000"),
            right=14, bottom=84,
            on_click=lambda e: dialogs.show_emergency(self),
        )
        page.overlay.append(self.sos)
        page.on_resize = self._on_resize

        self.map.light = saver
        self.map.on_pin = self._on_pin_dropped
        self.map.on_report_click = self.start_report
        self.map.on_report_here = self.report_at
        self.map.on_report_open = lambda r: dialogs.show_report_detail(self, r)
        self._apply_mode()
        self._sync_live()
        self.refresh()
        page.run_task(self.timer_loop)

    def build_ops(self):
        self.t_sensors = StatTile("Sensors online", "Smoke and weather nodes")
        self.t_fires = StatTile("Active detections", "No active ignitions")
        self.t_top = StatTile("Highest-risk zone", value_size=17)
        self.t_wind = StatTile("Wind")
        self.t_moist = StatTile("Avg. fuel moisture", "10-hr fuel class")

        stats = ft.ResponsiveRow(
            [
                ft.Container(content=x, col={"xs": 6, "sm": 4, "md": 2.4})
                for x in [
                    self.t_sensors,
                    self.t_fires,
                    self.t_top,
                    self.t_wind,
                    self.t_moist,
                ]
            ],
            spacing=16,
        )

        self.zone_list = ZoneList()
        self.zones_panel = zones_panel = card(
            ft.Column(
                [
                    txt("Zones by risk", 13, TEXT, bold=True),
                    ft.Divider(height=1, color=LINE_SOFT),
                    self.zone_list,
                ],
                spacing=8,
            ),
            padding=14,
            height=480,
        )

        self.map = FireMap()
        self.map_panel_meta = txt("", 11, FAINT)
        self.live_switch = ft.Switch(
            value=self.live, on_change=self.on_live_toggle, disabled=not firms.available(),
            tooltip=("Real fire detections from NASA satellites" if firms.available()
                     else "Needs the server version with a NASA FIRMS key"),
        )
        self.saver_switch = ft.Switch(
            value=self.saver, on_change=self.on_saver_toggle,
            tooltip="Slower updates and a lighter map, to save mobile data",
        )
        self.data_note = txt("", 11, FAINT)
        self.map_panel = map_panel = card(
            ft.Column(
                [
                    ft.Row(
                        [txt("South Africa sensor map", 13, TEXT, bold=True),
                         ft.Container(expand=True), self.map_panel_meta]
                    ),
                    ft.Row(
                        [self.live_switch, txt("Live NASA data", 12, DIM),
                         self.saver_switch, txt("Data saver", 12, DIM)],
                        spacing=4, run_spacing=0, wrap=True,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    self.data_note,
                    self.map,
                    ft.Row(
                        [
                            ft.Row([dot(RISK["low"]), txt("Low", 11.5, DIM)], spacing=5, tight=True),
                            ft.Row([dot(RISK["moderate"]), txt("Moderate", 11.5, DIM)], spacing=5, tight=True),
                            ft.Row([dot(RISK["high"]), txt("High", 11.5, DIM)], spacing=5, tight=True),
                            ft.Row([dot(RISK["extreme"]), txt("Extreme", 11.5, DIM)], spacing=5, tight=True),
                            ft.Row([dot(CONTAINED), txt("Contained", 11.5, DIM)], spacing=5, tight=True),
                            ft.Row([dot(HOTSPOT, 7), txt("NASA hotspot", 11.5, DIM)], spacing=5, tight=True),
                            ft.Row([ft.Icon(ft.Icons.LOCATION_ON, color=INFO_BLUE, size=14),
                                    txt("Citizen report", 11.5, DIM)], spacing=3, tight=True),
                            ft.Row([dot(EMERGENCY, 7), txt("Projected spread (indicative)", 11.5, DIM)], spacing=5, tight=True),
                            ft.Row([ft.Icon(ft.Icons.CAMPAIGN, color=EMERGENCY, size=14),
                                    txt("Station notice", 11.5, DIM)], spacing=3, tight=True),
                        ],
                        wrap=True, spacing=14, run_spacing=4,
                    ),
                    txt(
                        "Scroll, pinch or use + / − to zoom, drag to pan, or search for a place. "
                        "Search any town, township or village, or zoom in and tap the map for exact coordinates. "
                        "Tap the pin button to report smoke or fire.",
                        11,
                        FAINT,
                    ),
                ],
                spacing=8,
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            ),
            padding=10,
            height=480,
            expand=True,
        )

        self.feed_list = FeedList()
        self.feed_panel = feed_panel = card(
            ft.Column(
                [
                    txt("Event feed", 13, TEXT, bold=True),
                    ft.Divider(height=1, color=LINE_SOFT),
                    self.feed_list,
                ],
                spacing=8,
            ),
            padding=14,
            height=480,
        )

        main_grid = ft.ResponsiveRow(
            [
                ft.Container(content=zones_panel, col={"xs": 12, "lg": 3}),
                ft.Container(content=map_panel, col={"xs": 12, "lg": 6}),
                ft.Container(content=feed_panel, col={"xs": 12, "lg": 3}),
            ],
            spacing=12,
        )

        self.tr_wind = Trend("Wind speed (km/h)", WIND, 0, 70)
        self.tr_moist = Trend("Fuel moisture (%)", MOIST, 0, 26)

        self.trend_box = ft.Container(content=ft.Row([self.tr_wind, self.tr_moist], spacing=24))
        trends = card(
            ft.Column(
                [
                    txt(f"Environmental trends, last {MAX_HISTORY} readings", 13, TEXT, bold=True),
                    self.trend_box,
                ],
                spacing=10,
            ),
            padding=14,
        )

        return ft.Column(
            [stats, main_grid, trends],
            spacing=14,
        )

    def _on_resize(self, e=None):
        self._check_layout()
        self.page.update()

    def _check_layout(self):
        """Adapt sizes to the screen: phone (< 700 px wide), tablet or desktop."""
        width = self.page.width or 1000
        mobile = width < 700
        key = (mobile, int(width // 24))
        if key == self._layout_key:
            return
        mode_changed = self._layout_key is None or self._layout_key[0] != mobile
        self._layout_key = key
        self.mobile = mobile
        self.map.mobile = mobile

        self.holder.padding = 8 if mobile else 16
        self.zone_list.limit = 15 if mobile else 30
        if self.saver:
            self.zone_list.limit = min(self.zone_list.limit, 10)
        self.zones_panel.height = 340 if mobile else 480
        self.feed_panel.height = 300 if mobile else 480
        self.map_panel_meta.visible = not mobile
        if mobile:
            self.map_panel.height = None
            self.map_panel.expand = False
            self.map.expand = False
            self.map.height = max(260, min(440, width * 0.85))
        else:
            self.map_panel.height = 480
            self.map_panel.expand = True
            self.map.expand = True
            self.map.height = None

        for tr in (self.tr_wind, self.tr_moist):
            tr.expand = not mobile
        self.trend_box.content = (
            ft.Column([self.tr_wind, self.tr_moist], spacing=12) if mobile
            else ft.Row([self.tr_wind, self.tr_moist], spacing=24)
        )
        if mode_changed:
            self.header.mobile = mobile
            self.header.set_user(self.user)

    def stop(self, e=None):
        self.running = False

    async def timer_loop(self):
        while self.running:
            factor = (1.4 if self.mobile else 1.0) * (3.0 if self.saver else 1.0)
            await self._sleep(TICK_SECONDS * factor)
            if not self.running:
                break
            try:
                self._tick_n += 1
                self.sim.tick()
                self._sync_live()
                if not config.IN_BROWSER and self._tick_n % (12 if self.saver else 4) == 1:
                    await self._pull_reports()
                    await self._pull_notices()
                self.refresh()
            except Exception:
                # Usually the visitor left and the session closed; stop ticking.
                import traceback
                traceback.print_exc()
                self.running = False

    async def _sleep(self, seconds):
        import asyncio
        await asyncio.sleep(seconds)

    def refresh(self):
        self._check_layout()
        state = self.sim.snapshot()

        self.update_stats(state)
        self.zone_list.render(state["zones"], state["wind"]["speed"])
        self.map.render(state)
        self.map_panel_meta.value = f'tick {state["tick"]}, {state["server_time"]}'
        self._update_note()
        self.feed_list.render(state["feed"])
        self.tr_wind.set_data(state["wind_history"])
        self.tr_moist.set_data(state["moist_history"])

        if state["wind_history"]:
            self.tr_wind.value.value = f'{round(state["wind_history"][-1])} km/h'
            self.tr_moist.value.value = f'{state["moist_history"][-1]:.1f}%'

        self.public.render(state, self.user)
        self.page.update()

    def update_stats(self, state):
        zones = state["zones"]
        active = [f for f in state["fires"] if not f["contained"]]
        severe = any(f["severity"] == "extreme" for f in active)

        self.t_sensors.set(len(zones))

        names = [f["zone_name"] for f in active]
        if not names:
            sub = "No active ignitions"
        elif len(names) <= 2:
            sub = ", ".join(names)
        else:
            sub = f"{names[0]}, {names[1]} +{len(names)-2} more"

        self.t_fires.set(
            len(active),
            sub,
            RISK["extreme"] if severe else RISK["high"] if active else TEXT,
        )

        top = max(zones, key=lambda z: z["risk"])
        top_color = (
            RISK["extreme"] if top["risk_level"] == "extreme"
            else RISK["high"] if top["risk_level"] == "high"
            else TEXT
        )
        self.t_top.set(
            top["name"],
            f'{top["risk_level"].capitalize()}, score {top["risk"]:.2f}',
            top_color,
        )

        self.t_wind.set(
            f'{round(state["wind"]["speed"])} km/h',
            "from " + compass_dir(state["wind"]["dir"]),
        )

        avg = sum(z["moisture"] for z in zones) / len(zones)
        self.t_moist.set(f"{avg:.1f}%")

        if active:
            n = len(active)
            self.header.pill.set_state(True, f"{n} active detection{'s' if n != 1 else ''}")
        else:
            self.header.pill.set_state(False, "All systems nominal")

        self.header.clock.value = datetime.now().strftime("%H:%M:%S") + " local"

    def reset(self, e=None):
        self.sim = Simulation()
        if self.live:
            self.sim.set_live(True)
            self._live_key = None
            self._seen_hotspots = set()
            self._sync_live()
        self.refresh()

    def toggle_view(self, e=None):
        self.showing_public = not self.showing_public
        self.holder.content = self.public if self.showing_public else self.ops
        self.header.toggle_button.content = (
            "Console view" if self.showing_public else "Public view"
        )
        self.header.set_user(self.user)
        self.page.update()

    # -- accounts, alerts, helpers -----------------------------------------
    def set_user(self, user):
        self.user = user
        self._remember(user)
        self.header.set_user(user)
        self.map.user_zone_id = user["home_zone_id"] if user else None
        if user:
            self.sync_subscription(user)
        self.refresh()

    def _remember(self, user):
        """Keep the signed-in email in this browser so the person is recognised on the next visit."""
        if self.prefs is None:
            return
        value = user["email"] if (user and self.keep_signed_in) else ""
        self.page.run_task(self.prefs.set, "firewatch_me", value)

    def is_browser_build(self):
        return config.IN_BROWSER

    def sync_subscription(self, user):
        """Tell the server about this user's alert choice (server version only)."""
        if config.IN_BROWSER:
            return
        zone = next((z for z in self.sim.zones if z["id"] == user["home_zone_id"]), None)
        if zone:
            self.page.run_task(self._sync_subscription, dict(user), zone)

    async def _sync_subscription(self, user, zone):
        try:
            await asyncio.to_thread(alerts.sync_subscriber, user, zone)
        except Exception as err:
            print("alerts: could not save subscription:", err)

    # -- live NASA data -------------------------------------------------------
    def _apply_mode(self):
        if self.live:
            self.footer.value = ("Fire detections: NASA FIRMS satellites (VIIRS), refreshed about every "
                                 f"{config.REFRESH_MIN} minutes. Temperature, wind and fuel moisture are simulated.")
        else:
            self.footer.value = ("Simulated demo. Data is generated by a built-in Python simulation "
                                 "for illustration and does not reflect real conditions.")
        if places.available():
            self.footer.value += " " + places.ATTRIBUTION + "."

    def _sync_live(self):
        """Copy the newest NASA data (downloaded by monitor.py) into this session."""
        if not self.live:
            return
        snap = firms.snapshot()
        stamp = snap["fetched_at"]
        if stamp is None or stamp == self._live_key:
            return
        first = self._live_key is None
        self._live_key = stamp
        hotspots = snap["hotspots"]
        clusters = firms.cluster(hotspots, self.sim.zones)
        ids = {h["id"] for h in hotspots}
        if first:
            self.sim.log_event("info", "NASA FIRMS",
                               f"Live satellite data connected: {len(hotspots)} hotspots in the last "
                               f"{config.FIRMS_DAYS * 24} hours.")
        else:
            fresh, shown = ids - self._seen_hotspots, 0
            for c in clusters:
                new = len(fresh & c["ids"])
                if new and shown < 3:
                    self.sim.log_event("high", "Detection",
                                       f"NASA satellite detected {new} new hotspot(s) near "
                                       f"[b]{places.where(c['lat'], c['lon']) or c['zone_name'] + ', ' + c['province']}[/b].")
                    shown += 1
        self._seen_hotspots = ids
        self.map.hotspots = hotspots
        self.sim.set_live_fires(clusters)

    def _update_note(self):
        if not self.live:
            note = "Simulation mode"
        else:
            snap = firms.snapshot()
            if snap["fetched_at"] is None:
                note = "Live mode · waiting for NASA FIRMS data…"
            else:
                when = datetime.fromtimestamp(snap["fetched_at"]).strftime("%H:%M")
                note = f"NASA FIRMS · {len(snap['hotspots'])} hotspots · updated {when}"
                if snap["error"]:
                    note += " · offline, showing saved data"
                note += " · weather simulated"
        if self.map.reports:
            note += f" · {len(self.map.reports)} citizen report(s)"
        if not places.available():
            note += " · place database not built yet"
        self.data_note.value = note

    def on_live_toggle(self, e):
        want = bool(e.control.value)
        if want and not firms.available():
            e.control.value = False
            self.toast("Live NASA data needs the server version with a FIRMS key.")
            self.page.update()
            return
        self.live = want
        self.sim.set_live(want)
        self._live_key = None
        self._seen_hotspots = set()
        if not want:
            self.map.hotspots = []
        self._apply_mode()
        self._sync_live()
        self.refresh()

    def on_saver_toggle(self, e):
        self.saver = bool(e.control.value)
        self.map.light = self.saver
        self._layout_key = None
        self._check_layout()
        if self.prefs is not None:
            self.page.run_task(self.prefs.set, "firewatch_saver", "1" if self.saver else "0")
        self.map._redraw()
        self.refresh()
        self.toast("Data saver on: slower updates and a lighter map." if self.saver else "Data saver off.")

    # -- citizen reports ----------------------------------------------------------
    async def _pull_reports(self, force=False):
        try:
            rows = await asyncio.to_thread(reports.recent_reports, force, firms.snapshot()["hotspots"])
        except Exception:
            return
        self.map.reports = rows

    async def _pull_notices(self):
        try:
            self.map.notices = await asyncio.to_thread(incidents.active_notices)
        except Exception:
            pass

    def refresh_notices(self):
        if not config.IN_BROWSER:
            self.page.run_task(self._pull_notices)

    def open_safety(self):
        """'What to do now' for the signed-in user's town, or the town with the highest risk."""
        state = self.sim.snapshot()
        zone_id = self.user["home_zone_id"] if self.user else state["top_zone_id"]
        zone = next(z for z in state["zones"] if z["id"] == zone_id)
        screens.show_safety(self, zone["lat"], zone["lon"], "veld")

    async def pull_reports_now(self):
        await self._pull_reports(force=True)
        self.refresh()

    def start_report(self):
        if config.IN_BROWSER:
            self.toast("Citizen reports need the server version of Firewatch.")
            return
        if not self.user:
            self.toast("Log in to send a report.")
            dialogs.show_login(self)
            return
        self.map.begin_pin()

    def report_at(self, lat, lon):
        """'Report smoke or fire here' button on the coordinate card."""
        if config.IN_BROWSER:
            self.toast("Citizen reports need the server version of Firewatch.")
        elif not self.user:
            self.toast("Log in to send a report.")
            dialogs.show_login(self)
        else:
            dialogs.show_report(self, lat, lon)

    def _on_pin_dropped(self, lat, lon):
        dialogs.show_report(self, lat, lon)

    def toast(self, message):
        self.page.show_dialog(ft.SnackBar(content=ft.Text(message), duration=3500))

    def _redraw_map(self):
        self.map._redraw()

    def clear_dispatch(self):
        self.map.dispatch = None
        self._redraw_map()



async def main(page: ft.Page):
    page.add(ft.Text("Starting Firewatch..."))
    page.update()
    monitor.start()          # server only: downloads NASA data and sends alerts, once per process
    prefs, saver = None, False
    if page.web:
        # Running in a browser: keep accounts (and the data-saver choice) in the browser's storage.
        try:
            prefs = ft.SharedPreferences()
            raw = await asyncio.wait_for(prefs.get("firewatch_users"), timeout=5)
            auth.use_browser_storage(
                raw, lambda data: page.run_task(prefs.set, "firewatch_users", data))
            saver = (await asyncio.wait_for(prefs.get("firewatch_saver"), timeout=3)) == "1"
        except Exception:
            auth.use_browser_storage(None, None)     # fall back to in-memory for this visit
    page.clean()
    app = FirewatchApp(page, saver=saver, prefs=prefs)
    if prefs is not None:
        try:                                         # recognise a returning person without a new login
            me = await asyncio.wait_for(prefs.get("firewatch_me"), timeout=3)
            user = auth.find(me) if me else None
            if user:
                app.set_user(user)
                app.toast(f"Welcome back, {user['name'].split()[0]}.")
        except Exception:
            pass


if sys.platform == "emscripten":
    # Running inside the browser (flet build web, Pyodide): the page is already served,
    # so just hand the app to Flet. Do not try to open a window or start a server here.
    ft.run(main)
elif __name__ == "__main__":
    port = os.environ.get("PORT")
    if port:
        # Hosted (Render, Railway, etc. set PORT): serve as a web app.
        ft.run(main, view=ft.AppView.WEB_BROWSER, host="0.0.0.0", port=int(port))
    elif os.environ.get("FIREWATCH_VIEW") == "web":
        ft.run(main, view=ft.AppView.WEB_BROWSER)
    else:
        # Local: open the desktop window. Some Windows PCs (Smart App Control / AppLocker /
        # WDAC) block Flet's desktop viewer (WinError 4551). In that case open in the browser.
        try:
            ft.run(main)
        except OSError as err:
            print(f"Desktop window could not start ({err}).\nOpening in your web browser instead...")
            ft.run(main, view=ft.AppView.WEB_BROWSER)
