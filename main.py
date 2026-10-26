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
import shell as shell_mod
from firemap import FireMap
from simulation import TICK_SECONDS, Simulation
from ui import (
    DIM, EMERGENCY, FAINT, INFO_BLUE, LINE, LINE_SOFT, MOIST, PANEL, RISK, TEXT, WIND, BG, card, chip, txt,
)


# ---------------------------------------------------------------------------
# Reusable UI components
# ---------------------------------------------------------------------------

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
        self.levels = None       # risk-level filter: None or a set of levels
        self.rows = {}
        self.order = []
        self.limit = 30          # only the riskiest zones are drawn (fewer widgets = faster)

    def render(self, zones, wind_speed):
        ranked = sorted((z for z in zones if not self.levels or z["risk_level"] in self.levels),
                        key=lambda z: -z["risk"])[: self.limit]
        ids = [z["id"] for z in ranked]

        if ids != self.order:
            self.controls = []
            for zone in ranked:
                row = self.rows.setdefault(zone["id"], ZoneRow())
                self.controls.append(row)
            self.order = ids

        for zone in ranked:
            self.rows[zone["id"]].render(zone, wind_speed)


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
        if not page.web:                       # desktop window: use the Firewatch icon instead of Flet's
            try:
                page.window.icon = "icon.ico" if sys.platform == "win32" else "icon.png"
            except Exception:
                pass
        page.bgcolor = BG
        page.padding = 0
        page.theme_mode = ft.ThemeMode.LIGHT
        page.horizontal_alignment = ft.CrossAxisAlignment.STRETCH

        self.user = None
        self.station = None          # set after a station logs in to the console
        self.keep_signed_in = True   # remember the signed-in person in this browser
        self.mobile = False
        self._layout_key = None
        self.mode = None
        self.header = shell_mod.Header(self)
        self.ops = self.build_ops()
        self.mini = FireMap()           # small preview on the overview page
        self.public = PublicView()
        self.footer = txt("", 11, FAINT)

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
        self.shell = shell_mod.Shell(self)
        page.scroll = None
        page.add(self.shell)
        page.on_resize = self._on_resize

        self.map.light = saver
        self.map.on_pin = self._on_pin_dropped
        self.map.on_report_click = self.start_report
        self.map.on_report_here = self.report_at
        self.map.on_report_open = lambda r: dialogs.show_report_detail(self, r)
        self.mini.mobile = True
        self.mini.on_report_click = lambda: self.shell.navigate("map")
        self.mini.on_report_open = lambda r: dialogs.show_report_detail(self, r)
        self.mini.on_report_here = self.report_at
        self.mini.on_pin = self._on_pin_dropped
        self._apply_mode()
        self._sync_live()
        self.refresh()
        page.run_task(self.timer_loop)

    def build_ops(self):
        """Create the map and the zone list. The pages that show them are built in shell.py."""
        self.zone_list = ZoneList()
        self.map = FireMap()
        self.data_note = txt("", 11.5, DIM)
        self.tr_wind = Trend("Wind speed (km/h)", WIND, 0, 70)
        self.tr_moist = Trend("Fuel moisture (%)", MOIST, 0, 26)
        return None

    def _on_resize(self, e=None):
        self._check_layout()
        self.page.update()

    def _check_layout(self):
        """Adapt sizes to the screen: phone (< 700 px wide), tablet or desktop."""
        width = self.page.width or 1000
        mode = shell_mod.mode_for(width, self.page.height)
        mobile = mode in ("phone", "watch")
        key = (mode, int(width // 24))
        if key == self._layout_key:
            return
        self._layout_key = key
        self.mode = mode
        self.mobile = mobile
        self.map.mobile = mobile
        self.shell.apply(mode, width)
        self.zone_list.limit = 15 if mobile else 30
        if self.saver:
            self.zone_list.limit = min(self.zone_list.limit, 10)
        self.shell.fit(mode, width)

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

        cur = self.shell.current
        if cur == "map":
            self.zone_list.render(state["zones"], state["wind"]["speed"])
            self.map.render(state)
        elif cur == "overview" and self.mode != "watch":
            for name in ("hotspots", "reports", "notices", "user_zone_id", "light"):
                setattr(self.mini, name, getattr(self.map, name))
            self.mini.render(state)
        self._update_note()
        self.tr_wind.set_data(state["wind_history"])
        self.tr_moist.set_data(state["moist_history"])
        if state["wind_history"]:
            self.tr_wind.value.value = f'{round(state["wind_history"][-1])} km/h'
            self.tr_moist.value.value = f'{state["moist_history"][-1]:.1f}%'

        self.public.render(state, self.user)
        self.shell.update_state(state, self.user)
        self.page.update()

    def reset(self, e=None):
        self.sim = Simulation()
        if self.live:
            self.sim.set_live(True)
            self._live_key = None
            self._seen_hotspots = set()
            self._sync_live()
        self.refresh()

    def toggle_view(self, e=None):
        self.shell.navigate("overview" if self.showing_public else "public")

    # -- accounts, alerts, helpers -----------------------------------------
    def set_user(self, user):
        self.user = user
        self._remember(user)
        self.shell.set_user(user)
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
    start = (page.route or "/").strip("/").split("/")[0]       # deep link, e.g. /map or /about
    if start in shell_mod.PAGES:
        app.shell.navigate(start)
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
