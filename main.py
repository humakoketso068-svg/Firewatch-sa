

import asyncio
import os
import sys
from datetime import datetime

import flet as ft

import auth
import dialogs
from firemap import FireMap
from simulation import MAX_HISTORY, TICK_SECONDS, Simulation
from ui import (
    CONTAINED, DARK, DIM, EMERGENCY, EMERGENCY_DARK, FAINT, FEED_COLOR, INFO_BLUE,
    LINE, LINE_SOFT, MOIST, PANEL, RISK, TEXT, WIND, BG, card, chip, compass_dir,
    dot, primary_button, txt,
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
            f'{round(zone["moisture"])}% moisture, wind {round(wind_speed)} mph'
        )
        self.bar.set(zone["risk"], RISK[zone["risk_level"]])


class ZoneList(ft.ListView):
    def __init__(self):
        super().__init__(expand=True, spacing=0, auto_scroll=False)
        self.rows = {}
        self.order = []

    def render(self, zones, wind_speed):
        ranked = sorted(zones, key=lambda z: -z["risk"])
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
        self.bars = ft.Row(spacing=1, vertical_alignment=ft.CrossAxisAlignment.END, expand=True)
        super().__init__(
            content=ft.Column(
                [
                    ft.Row(
                        [self.title, ft.Container(expand=True), self.value],
                        tight=True,
                    ),
                    ft.Container(content=self.bars, height=65, alignment=ft.Alignment.BOTTOM_LEFT),
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
                    expand=True,
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
        # Three-line menu: Log in / Sign up (or profile / log out once signed in).
        self.menu = ft.PopupMenuButton(icon=ft.Icons.MENU, icon_size=24, tooltip="Menu", items=[])
        self.buttons = ft.Row(alignment=ft.MainAxisAlignment.END, wrap=True, spacing=8, run_spacing=6,
                              vertical_alignment=ft.CrossAxisAlignment.CENTER)
        self.subtitle = txt("Live sensor fusion and fire-spread projection, South Africa", 12, DIM)
        self.title_row = ft.Row(vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=4)
        self.title_block = ft.Column(
            [ft.Row([dot(TEXT, 9), txt("Firewatch", 19, TEXT, bold=True)], spacing=8, tight=True),
             self.subtitle],
            spacing=2, tight=True, expand=True,
        )
        self.compact = False

        super().__init__(
            content=ft.ResponsiveRow(
                [
                    ft.Container(col={"xs": 12, "md": 5}, content=self.title_row),
                    ft.Container(col={"xs": 12, "md": 7}, content=self.buttons),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                run_spacing=6,
            ),
            bgcolor=PANEL,
            padding=ft.Padding.symmetric(horizontal=14, vertical=10),
            border=ft.Border.only(bottom=ft.BorderSide(1, LINE)),
        )
        self.set_user(None)

    def set_user(self, user):
        app = self.app
        if user is None:
            items = [
                ft.PopupMenuItem(content="Log in", icon=ft.Icons.LOGIN,
                                 on_click=lambda e: dialogs.show_login(app)),
                ft.PopupMenuItem(content="Sign up", icon=ft.Icons.PERSON_ADD,
                                 on_click=lambda e: dialogs.show_signup(app)),
            ]
        else:
            items = [
                ft.PopupMenuItem(content=f"Signed in as {user['name'].split()[0]}",
                                 icon=ft.Icons.ACCOUNT_CIRCLE, disabled=True),
                ft.PopupMenuItem(content="My profile", icon=ft.Icons.PERSON,
                                 on_click=lambda e: dialogs.show_profile(app)),
                ft.PopupMenuItem(content="Log out", icon=ft.Icons.LOGOUT,
                                 on_click=lambda e: (app.set_user(None), app.toast("You have been logged out."))),
            ]
        self.menu.items = items
        self.set_compact(self.compact)

    def set_compact(self, compact):
        """Phone layout: menu sits next to the title, clock is hidden, buttons are small."""
        self.compact = compact
        self.subtitle.visible = not compact
        self.clock.visible = not compact
        small = ft.ButtonStyle(padding=ft.Padding.symmetric(horizontal=12, vertical=0))
        for b in (self.reset_button, self.toggle_button):
            b.style = small if compact else None
        self.buttons.alignment = ft.MainAxisAlignment.START if compact else ft.MainAxisAlignment.END
        if compact:
            self.title_row.controls = [self.title_block, self.menu]
            self.buttons.controls = [self.pill, self.reset_button, self.toggle_button]
        else:
            self.title_row.controls = [self.title_block]
            self.buttons.controls = [self.clock, self.pill, self.reset_button, self.toggle_button, self.menu]


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
    def __init__(self, page: ft.Page):
        self.page = page
        self.sim = Simulation()
        self.showing_public = False
        self.running = True
        self.seen_fires = set()       # fire ids already announced
        self.alert_queue = []         # new fires waiting for a popup
        self.alert_showing = False
        page.on_close = self.stop

        page.title = "Firewatch — Live Detection Console"
        page.bgcolor = BG
        page.padding = 0
        page.theme_mode = ft.ThemeMode.LIGHT
        page.scroll = ft.ScrollMode.AUTO
        page.horizontal_alignment = ft.CrossAxisAlignment.STRETCH

        self.user = None
        self.header = Header(self)
        self.ops = self.build_ops()
        self.public = PublicView()

        self.holder = ft.Container(content=self.ops, padding=16)
        self.footer = ft.Container(
            content=txt(
                "Simulated demo. Data is generated by a built-in Python simulation "
                "for illustration and does not reflect real conditions.",
                11, FAINT,
            ),
            alignment=ft.Alignment.CENTER,
            padding=ft.Padding.only(left=16, right=16, top=4, bottom=90),   # room for SOS / host badges
        )
        self.footer.content.text_align = ft.TextAlign.CENTER

        # Floating round SOS button: stays on screen while scrolling, tucked into the
        # bottom-left corner so it never covers the map's zoom controls, the event
        # feed or hosting badges that sit bottom-right.
        page.floating_action_button = ft.FloatingActionButton(
            content=ft.Column(
                [ft.Icon(ft.Icons.WARNING_AMBER_ROUNDED, color="#FFFFFF", size=24),
                 ft.Text("SOS", size=10, weight=ft.FontWeight.BOLD, color="#FFFFFF")],
                spacing=0, tight=True, alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            bgcolor=EMERGENCY, shape=ft.CircleBorder(), width=62, height=62,
            tooltip="Emergency alert", elevation=6,
            on_click=lambda e: dialogs.show_emergency(self),
        )
        page.floating_action_button_location = ft.FloatingActionButtonLocation.START_FLOAT

        page.add(self.header, self.holder, self.footer)

        page.on_resize = self.apply_layout
        self.apply_layout()
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
        self.map_hint = txt(
            "Pinch or use + / − to zoom, drag to pan, or search for a place. "
            "Rings show the simulated evacuation advisory radius.", 11, FAINT)
        self.map_panel = map_panel = card(
            ft.Column(
                [
                    ft.Row(
                        [txt("South Africa sensor map", 13, TEXT, bold=True),
                         ft.Container(expand=True), self.map_panel_meta,
                        ]
                    ),
                    self.map,
                    ft.Row(
                        [
                            ft.Row([dot(RISK["low"]), txt("Low", 11.5, DIM)], spacing=5),
                            ft.Row([dot(RISK["moderate"]), txt("Moderate", 11.5, DIM)], spacing=5),
                            ft.Row([dot(RISK["high"]), txt("High", 11.5, DIM)], spacing=5),
                            ft.Row([dot(RISK["extreme"]), txt("Extreme", 11.5, DIM)], spacing=5),
                            ft.Row([dot(CONTAINED), txt("Contained", 11.5, DIM)], spacing=5),
                        ],
                        wrap=True, spacing=12, run_spacing=4,
                    ),
                    self.map_hint,
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

        self.tr_wind = Trend("Wind speed (mph)", WIND, 0, 45)
        self.tr_moist = Trend("Fuel moisture (%)", MOIST, 0, 26)

        trends = card(
            ft.Column(
                [
                    txt(f"Environmental trends, last {MAX_HISTORY} readings", 13, TEXT, bold=True),
                    ft.ResponsiveRow(
                        [ft.Container(self.tr_wind, col={"xs": 12, "sm": 6}),
                         ft.Container(self.tr_moist, col={"xs": 12, "sm": 6})],
                        spacing=16, run_spacing=10),
                ],
                spacing=10,
            ),
            padding=14,
        )

        return ft.Column(
            [stats, main_grid, trends],
            spacing=14,
        )

    def apply_layout(self, e=None):
        """Adapt sizes to the screen: phone (<600), tablet (<1000) or desktop."""
        w = self.page.width or 1000
        h = self.page.height or 800
        phone, tablet = w < 600, w < 1000
        self.phone = phone

        self.holder.padding = 10 if phone else 16
        self.header.set_compact(phone)
        # Phones: let the map be tall and square-ish; lists get a shorter fixed height so
        # the page scrolls instead of trapping the finger inside nested lists.
        map_h = max(380, min(560, int(h * 0.62))) if phone else 480
        side_h = 300 if phone else (380 if tablet else 480)
        self.map_panel.height = map_h + 90 if phone else map_h     # + title row and legend
        self.zones_panel.height = side_h
        self.feed_panel.height = side_h
        self.map_hint.visible = not phone
        self.map.set_compact(phone, w)
        try:
            self.page.update()
        except Exception:
            pass

    def stop(self, e=None):
        self.running = False

    async def timer_loop(self):
        while self.running:
            await self._sleep(TICK_SECONDS)
            if not self.running:
                break
            try:
                self.sim.tick()
                self.refresh()
                self.check_alerts()
            except Exception:
                # The session was closed (visitor left); stop ticking.
                self.running = False

    async def _sleep(self, seconds):
        import asyncio
        await asyncio.sleep(seconds)

    def refresh(self):
        state = self.sim.snapshot()

        self.update_stats(state)
        self.zone_list.render(state["zones"], state["wind"]["speed"])
        self.map.render(state)
        self.map_panel_meta.value = f'tick {state["tick"]}, {state["server_time"]}'
        self.feed_list.render(state["feed"])
        self.tr_wind.set_data(state["wind_history"])
        self.tr_moist.set_data(state["moist_history"])

        if state["wind_history"]:
            self.tr_wind.value.value = f'{round(state["wind_history"][-1])} mph'
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
            f'{round(state["wind"]["speed"])} mph',
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
        self.seen_fires.clear()
        self.alert_queue.clear()
        self.refresh()

    def toggle_view(self, e=None):
        self.showing_public = not self.showing_public
        self.holder.content = self.public if self.showing_public else self.ops
        self.header.toggle_button.content = (
            "Console view" if self.showing_public else "Public view"
        )
        self.page.update()

    # -- accounts, alerts, helpers -----------------------------------------
    def set_user(self, user):
        self.user = user
        self.header.set_user(user)
        self.map.user_zone_id = user["home_zone_id"] if user else None
        self.refresh()

    # -- fire alert popups ---------------------------------------------------
    def _other_dialog_open(self):
        """True while the user is in another dialog (login, emergency form, ...)."""
        try:
            return any(isinstance(d, ft.AlertDialog) and d.open for d in self.page._dialogs.controls)
        except Exception:
            return False

    def check_alerts(self):
        """Queue newly detected fires, then show one popup (batched) if the user is free."""
        stamp = datetime.now().strftime("%H:%M:%S")
        for f in self.sim.fires:
            if not f["contained"] and f["id"] not in self.seen_fires:
                self.seen_fires.add(f["id"])
                self.alert_queue.append({**f, "ts": stamp})
        if self.alert_queue and not self.alert_showing and not self._other_dialog_open():
            batch, self.alert_queue = self.alert_queue, []
            self.alert_showing = True
            dialogs.show_fire_alert(self, batch)

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
    if page.web:
        # Running in a browser (e.g. deployed on Vercel): keep accounts in the browser's storage.
        try:
            prefs = ft.SharedPreferences()
            raw = await asyncio.wait_for(prefs.get("firewatch_users"), timeout=5)
            auth.use_browser_storage(
                raw, lambda data: page.run_task(prefs.set, "firewatch_users", data))
        except Exception:
            auth.use_browser_storage(None, None)     # fall back to in-memory for this visit
    page.clean()
    FirewatchApp(page)


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
