"""
Interactive South Africa map: zoom buttons, mouse-wheel / pinch zoom, drag to pan,
double-click to zoom, "find a place" search, and collision-free place names that
fill in as you zoom closer.
"""

import time

import flet as ft
import flet.canvas as cv

import places

from geo import (
    ESWATINI, LABELLED, LAT_MIN, LESOTHO, LON_MIN, PAD_X, PAD_Y, PROVINCE_LABELS,
    PX_PER_LAT, PX_PER_LON, SA_OUTLINE, VIEW_H, VIEW_W, project,
)
from ui import (
    CONTAINED, DIM, EMERGENCY, FAINT, INFO_BLUE, LAND, LAND_EDGE, LINE, MAP_BG,
    PANEL, PROVINCE_TEXT, RISK, TEXT, WIND, txt, HOTSPOT, age_text, fmt_coord,
)

# Neighbouring countries and oceans, as (name, lat, lon).
CONTEXT_LABELS = [
    ("NAMIBIA", -27.3, 17.9), ("BOTSWANA", -23.2, 23.6),
    ("MOZAMBIQUE", -24.6, 33.5), ("LESOTHO", -29.55, 28.2), ("ESWATINI", -26.55, 31.45),
    ("ATLANTIC OCEAN", -32.0, 15.1), ("INDIAN OCEAN", -33.6, 31.2),
]

MIN_ZOOM, MAX_ZOOM = 1.0, 9.0
KM_PER_DEG_LAT = 111.0
NICE_KM = [5, 10, 20, 25, 50, 100, 200, 500]


def short_name(name):
    return name.split(" (")[0]


class FireMap(ft.Container):
    def __init__(self):
        self.state = None
        self.zoom = 1.0
        self.cx, self.cy = VIEW_W / 2, VIEW_H / 2   # view-space point at the middle of the screen
        self.avail_w, self.avail_h = VIEW_W, VIEW_H
        self.user_zone_id = None
        self.dispatch = None          # {"origin": (x, y), "stations": [...], "done": set()}
        self._ptr = (VIEW_W / 2, VIEW_H / 2)
        self._base_zoom = 1.0
        self._last_draw = 0.0
        self._search_ready = False
        self.mobile = False
        self._gest_on = True
        self.hotspots = []            # NASA FIRMS detections
        self.reports = []             # citizen reports
        self.pin_mode = False         # waiting for the user to tap a spot
        self.pending_pin = None
        self.light = False            # data-saver: fewer labels and effects
        self.on_pin = None            # callback(lat, lon)
        self.on_report_click = None
        self.on_report_here = None    # callback(lat, lon)
        self.selected = None          # place or spot shown in the coordinate card
        self._results = []
        self._view = (1.0, 0.0, 0.0)  # (scale, ox, oy) of the last draw, for tap -> lat/lon

        self.map_stack = ft.Stack(
            width=VIEW_W, height=VIEW_H, clip_behavior=ft.ClipBehavior.HARD_EDGE,
        )
        gestures = self.gestures = ft.GestureDetector(
            content=self.map_stack,
            on_scroll=self._on_scroll,
            on_hover=self._on_hover,
            on_scale_start=self._on_scale_start,
            on_scale_update=self._on_scale_update,
            on_double_tap_down=self._on_double_tap_down,
            on_tap_up=self._on_tap_up,
        )

        self.zoom_label = txt("100%", 10.5, DIM, bold=True)
        self.search = ft.TextField(
            hint_text="Find a town, township or village…", width=210, dense=True, text_size=12,
            border_radius=8, prefix_icon=ft.Icons.SEARCH, bgcolor=PANEL,
            on_change=self._on_search_change, on_submit=self._on_search_submit,
        )
        self.results = ft.Column(spacing=0, tight=True)
        self.results_panel = ft.Container(
            content=self.results, left=10, top=52, width=210, visible=False, bgcolor=PANEL,
            border=ft.Border.all(1, LINE), border_radius=8, padding=ft.Padding.symmetric(vertical=4),
        )
        self.controls_panel = ft.Container(
            content=ft.Column(
                [
                    self._btn(ft.Icons.ADD, "Zoom in", lambda e: self.zoom_by(1.5)),
                    ft.Container(content=self.zoom_label, alignment=ft.Alignment.CENTER, width=40),
                    self._btn(ft.Icons.REMOVE, "Zoom out", lambda e: self.zoom_by(1 / 1.5)),
                    ft.Divider(height=1, color=LINE),
                    self._btn(ft.Icons.HOME, "Reset view", lambda e: self.reset_view()),
                    self._btn(ft.Icons.LOCAL_FIRE_DEPARTMENT, "Zoom to active fires",
                              lambda e: self.focus_fires(), color=EMERGENCY),
                    self._btn(ft.Icons.ADD_LOCATION_ALT, "Report smoke or fire",
                              lambda e: self.on_report_click and self.on_report_click(), color=INFO_BLUE),
                ],
                spacing=0, tight=True, horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            right=10, top=10, bgcolor=PANEL, border=ft.Border.all(1, LINE), border_radius=10,
            padding=ft.Padding.symmetric(vertical=4),
        )
        self.search_panel = ft.Container(content=self.search, left=10, top=10)

        super().__init__(
            content=gestures,
            bgcolor=MAP_BG, border=ft.Border.all(1, LINE), border_radius=8,
            expand=True, clip_behavior=ft.ClipBehavior.HARD_EDGE,
            on_size_change=self._on_size_change,
        )

    # -- small helpers ---------------------------------------------------
    @staticmethod
    def _btn(icon, tip, handler, color=TEXT):
        return ft.IconButton(icon=icon, tooltip=tip, on_click=handler, icon_size=20, icon_color=color)

    @property
    def fit(self):
        return max(0.35, min(self.avail_w / VIEW_W, self.avail_h / VIEW_H))

    def _pos(self, x, y, scale, ox, oy):
        return ox + x * scale, oy + (VIEW_H - y) * scale

    def _sync_gestures(self):
        """On a phone, leave one-finger drags to the page (so you can scroll past the map)
        until the map is zoomed in; then dragging pans the map."""
        want = (not self.mobile) or self.zoom > 1.001
        if want == self._gest_on:
            return
        self._gest_on = want
        g = self.gestures
        g.on_scroll = self._on_scroll if want else None
        g.on_scale_start = self._on_scale_start if want else None
        g.on_scale_update = self._on_scale_update if want else None
        try:
            g.update()
        except Exception:
            pass

    def _redraw(self, throttle=False):
        if self.state is None:
            return
        now = time.monotonic()
        if throttle and now - self._last_draw < 0.05:
            return
        self._last_draw = now
        self.render(self.state)
        try:
            self.map_stack.update()
        except Exception:
            pass

    # -- zoom / pan ------------------------------------------------------
    def _clamp(self):
        self.zoom = max(MIN_ZOOM, min(MAX_ZOOM, self.zoom))
        if self.zoom <= MIN_ZOOM + 1e-3:
            self.cx, self.cy = VIEW_W / 2, VIEW_H / 2
        else:
            self.cx = max(0, min(VIEW_W, self.cx))
            self.cy = max(0, min(VIEW_H, self.cy))

    def _zoom_at(self, new_zoom, px, py):
        """Zoom so the map point under screen position (px, py) stays put."""
        old_scale = self.fit * self.zoom
        vx = self.cx + (px - self.avail_w / 2) / old_scale
        vy = self.cy - (py - self.avail_h / 2) / old_scale
        self.zoom = max(MIN_ZOOM, min(MAX_ZOOM, new_zoom))
        new_scale = self.fit * self.zoom
        self.cx = vx - (px - self.avail_w / 2) / new_scale
        self.cy = vy + (py - self.avail_h / 2) / new_scale
        self._clamp()

    def zoom_by(self, factor):
        self._zoom_at(self.zoom * factor, self.avail_w / 2, self.avail_h / 2)
        self._redraw()

    def reset_view(self):
        self.zoom, self.cx, self.cy = 1.0, VIEW_W / 2, VIEW_H / 2
        self._redraw()

    def focus_on(self, x, y, zoom=4.0):
        self.zoom, self.cx, self.cy = zoom, x, y
        self._clamp()
        self._redraw()

    def focus_fires(self):
        active = [f for f in (self.state or {}).get("fires", []) if not f["contained"]]
        if not active:
            self.reset_view()
            return
        xs, ys = [f["x"] for f in active], [f["y"] for f in active]
        span = max(max(xs) - min(xs), max(ys) - min(ys), 40)
        self.focus_on(sum(xs) / len(xs), sum(ys) / len(ys),
                      max(1.5, min(5.0, min(VIEW_W, VIEW_H) / (span * 1.8))))

    # -- dropping a pin for a citizen report -----------------------------
    def begin_pin(self):
        self.pin_mode = True
        self.pending_pin = None
        self._redraw()

    def cancel_pin(self, e=None):
        self.pin_mode = False
        self.pending_pin = None
        self._redraw()

    def screen_to_latlon(self, px, py):
        scale, ox, oy = self._view
        x = (px - ox) / scale
        y = VIEW_H - (py - oy) / scale
        return LAT_MIN + (y - PAD_Y) / PX_PER_LAT, LON_MIN + (x - PAD_X) / PX_PER_LON

    def _on_tap_up(self, e):
        lat, lon = self.screen_to_latlon(e.local_position.x, e.local_position.y)
        if self.pin_mode:                                   # placing a citizen-report pin
            self.pin_mode = False
            self.pending_pin = (lat, lon)
            self._redraw()
            if self.on_pin:
                self.on_pin(lat, lon)
            return
        if self.zoom >= 2.5:                                # tap = "what is here?"
            self.selected = self._describe(lat, lon)
            self._redraw()

    # -- place search and the coordinate card ---------------------------------
    def _nearest_zone(self, lat, lon):
        best, best_km = None, 1e9
        for zone in (self.state or {}).get("zones", []):
            km = places.distance_km(lat, lon, zone["lat"], zone["lon"])
            if km < best_km:
                best, best_km = zone, km
        return best, best_km

    def _spot_tip(self, spot):
        where = places.where(spot["lat"], spot["lon"])
        head = "NASA hotspot" + (f" · {where}" if where else "")
        return (f'{head}\n{fmt_coord(spot["lat"], spot["lon"])}\n'
                f'{spot["conf"]} confidence · {spot["frp"]:.0f} MW · {age_text(spot["ts"])}')

    def _describe(self, lat, lon, name=None, province=None):
        near, km = places.nearest(lat, lon, 30)
        zone, zkm = self._nearest_zone(lat, lon)
        note = None
        if name is None:
            if near and km <= 2.5:
                name, province = near["name"], near["province"]
            else:
                name = "Selected spot"
                province = near["province"] if near else (zone["province"] if zone else "")
                if near:
                    note = f'Nearest named place: {near["name"]}, {km:.0f} km away'
        sensor = f'Nearest sensor town: {short_name(zone["name"])}, {zkm:.0f} km away' if zone else None
        return {"name": name, "province": province or "", "lat": lat, "lon": lon, "note": note, "sensor": sensor}

    def _clear_selected(self, e=None):
        self.selected = None
        self._redraw()

    def _on_search_change(self, e):
        self._show_results(" ".join((self.search.value or "").lower().split()))

    def _on_search_submit(self, e):
        if self._results:
            self._choose(self._results[0])

    def _show_results(self, q):
        rows = []
        if len(q) >= 2:
            for zone in (self.state or {}).get("zones", []):      # the sensor towns first
                name = short_name(zone["name"])
                if name.lower().startswith(q):
                    rows.append({"name": name, "province": zone["province"], "lat": zone["lat"], "lon": zone["lon"]})
            seen = {(r["name"].lower(), r["province"]) for r in rows}
            for p in places.search(q, 8):
                if (p["name"].lower(), p["province"]) not in seen:
                    rows.append(p)
            rows = rows[:8]
        self._results = rows
        items = [
            ft.Container(
                content=ft.Column([
                    txt(r["name"], 12.5, TEXT, bold=True),
                    txt(f'{r["province"]} · {fmt_coord(r["lat"], r["lon"])}', 10.5, DIM),
                ], spacing=0, tight=True),
                padding=ft.Padding.symmetric(horizontal=10, vertical=5), ink=True,
                on_click=lambda e, r=r: self._choose(r))
            for r in rows
        ]
        if len(q) >= 2 and not rows:
            hint = ("No match. Try another spelling." if places.available() else
                    "Place database not installed yet, so only the sensor towns can be searched.")
            items.append(ft.Container(content=txt(hint, 11.5, DIM), padding=10))
        self.results.controls = items
        self.results_panel.visible = bool(items)
        try:
            self.results_panel.update()
        except Exception:
            self._redraw()

    def _choose(self, r):
        self.search.value = r["name"]
        self.results_panel.visible = False
        self.selected = self._describe(r["lat"], r["lon"], name=r["name"], province=r["province"])
        x, y = project(r["lat"], r["lon"])
        self.focus_on(x, y, 6.0)

    def _on_hover(self, e):
        self._ptr = (e.local_position.x, e.local_position.y)

    def _on_scroll(self, e):
        dy = e.scroll_delta.y
        if dy:
            px, py = self._ptr
            self._zoom_at(self.zoom * (0.87 if dy > 0 else 1.15), px, py)
            self._redraw(throttle=True)

    def _on_double_tap_down(self, e):
        self._zoom_at(self.zoom * 1.8, e.local_position.x, e.local_position.y)
        self._redraw()

    def _on_scale_start(self, e):
        self._base_zoom = self.zoom

    def _on_scale_update(self, e):
        scale = self.fit * self.zoom
        self.cx -= e.focal_point_delta.x / scale
        self.cy += e.focal_point_delta.y / scale
        if e.pointer_count >= 2 and abs(e.scale - 1) > 0.01:      # pinch (touch screens)
            self._zoom_at(self._base_zoom * e.scale, e.local_focal_point.x, e.local_focal_point.y)
        self._clamp()
        self._redraw(throttle=True)

    def _on_size_change(self, e):
        if e.width < 20 or e.height < 20:
            return
        if abs(e.width - self.avail_w) < 1 and abs(e.height - self.avail_h) < 1:
            return
        self.avail_w, self.avail_h = e.width, e.height
        self.search.width = max(120, min(250, e.width - 76))
        self.results_panel.width = self.search.width
        self._redraw()

    # -- drawing -----------------------------------------------------------
    def _polygon(self, latlon_points, fill, scale, ox, oy):
        pts = [self._pos(*project(lat, lon), scale, ox, oy) for lat, lon in latlon_points]
        path = [cv.Path.MoveTo(*pts[0])] + [cv.Path.LineTo(x, y) for x, y in pts[1:]] + [cv.Path.Close()]
        return [
            cv.Path(path, ft.Paint(color=fill, style=ft.PaintingStyle.FILL)),
            cv.Path(path, ft.Paint(color=LAND_EDGE, style=ft.PaintingStyle.STROKE, stroke_width=1.2)),
        ]

    def render(self, state):
        self.state = state
        self._sync_gestures()
        w, h = self.avail_w, self.avail_h
        fit = self.fit
        scale = fit * self.zoom
        ms = min(scale, fit * 1.7)                      # marker scale: markers grow slower than the map
        ox = w / 2 - self.cx * scale
        oy = h / 2 - (VIEW_H - self.cy) * scale
        self._view = (scale, ox, oy)
        self.zoom_label.value = f"{round(self.zoom * 100)}%"

        def visible(px, py, m=30):
            return -m <= px <= w + m and -m <= py <= h + m

        shapes = self._polygon(SA_OUTLINE, LAND, scale, ox, oy)
        shapes += self._polygon(LESOTHO, MAP_BG, scale, ox, oy)
        shapes += self._polygon(ESWATINI, MAP_BG, scale, ox, oy)

        # Dispatch lines (emergency alert) go on the canvas under the markers.
        if self.dispatch:
            o = self._pos(*self.dispatch["origin"], scale, ox, oy)
            for s in self.dispatch["stations"]:
                sx, sy = self._pos(s["x"], s["y"], scale, ox, oy)
                done = s["id"] in self.dispatch["done"]
                shapes.append(cv.Line(
                    o[0], o[1], sx, sy,
                    ft.Paint(color=EMERGENCY if done else LAND_EDGE, stroke_width=1.3 if done else 0.8,
                             style=ft.PaintingStyle.STROKE),
                ))
        controls = [cv.Canvas(shapes=shapes, left=0, top=0, width=w, height=h)]

        # Province names fade out once you are zoomed in close.
        # Font size follows the map size, and a label is skipped if it would overlap
        # another province label, so names never pile on top of each other.
        if self.zoom < 3.2 and not self.light:
            pfont = max(6.0, (6.0 + min(self.zoom, 2.5) * 1.3) * min(1.0, fit + 0.2))
            taken = []
            for name, lat, lon in PROVINCE_LABELS:
                px, py = self._pos(*project(lat, lon), scale, ox, oy)
                if not visible(px, py, 60):
                    continue
                pw, ph = len(name) * pfont * 0.72, pfont + 4
                rect = (px - pw / 2, py - ph / 2, px + pw / 2, py + ph / 2)
                if any(rect[0] < b[2] and rect[2] > b[0] and rect[1] < b[3] and rect[3] > b[1] for b in taken):
                    continue
                taken.append(rect)
                controls.append(ft.Container(
                    content=txt(name.upper(), pfont, PROVINCE_TEXT, bold=True),
                    left=px - 60, top=py - ph / 2, width=120, alignment=ft.Alignment.CENTER))
        if self.zoom < 4 and not self.light:
            for name, lat, lon in CONTEXT_LABELS:
                px, py = self._pos(*project(lat, lon), scale, ox, oy)
                if visible(px, py, 60):
                    controls.append(ft.Container(
                        content=txt(name, 8 + min(self.zoom, 2), "#9AA7B2"),
                        left=px - 60, top=py - 7, width=120, alignment=ft.Alignment.CENTER))

        # Fires
        for fire in state["fires"]:
            fx, fy = self._pos(fire["x"], fire["y"], scale, ox, oy)
            if not visible(fx, fy, 200):
                continue
            radius = fire["radius"] * scale
            size = max(8, radius * 1.4)
            color = CONTAINED if fire["contained"] else RISK[fire["severity"]]
            if not fire["contained"] and fire["severity"] == "extreme" and not self.light:
                ring = max(20, radius * 2.1)
                controls.append(ft.Container(
                    left=fx - ring, top=fy - ring, width=ring * 2, height=ring * 2,
                    border=ft.Border.all(1, RISK["extreme"]), border_radius=ring, opacity=0.55))
            controls.append(ft.Container(
                left=fx - size / 2, top=fy - size / 2, width=size, height=size,
                bgcolor=color, opacity=0.22, border_radius=size / 2))
            core = max(8, 10 * ms)
            controls.append(ft.Container(
                left=fx - core / 2, top=fy - core / 2, width=core, height=core,
                bgcolor=color, border_radius=core / 2))

        # NASA FIRMS satellite hotspots
        if self.hotspots:
            budget, drawn = (250 if self.light else 600), 0
            hs_size = max(5.0, 5.5 * ms)
            for spot in self.hotspots:
                if drawn >= budget:
                    break
                hx, hy = self._pos(*project(spot["lat"], spot["lon"]), scale, ox, oy)
                if not visible(hx, hy, 8):
                    continue
                drawn += 1
                if not self.light:
                    halo = hs_size * 2.4
                    controls.append(ft.Container(
                        left=hx - halo / 2, top=hy - halo / 2, width=halo, height=halo,
                        bgcolor=HOTSPOT, opacity=0.16, border_radius=halo / 2))
                controls.append(ft.Container(
                    left=hx - hs_size / 2, top=hy - hs_size / 2, width=hs_size, height=hs_size,
                    bgcolor=HOTSPOT, border=ft.Border.all(0.8, "#FFFFFF"), border_radius=hs_size / 2,
                    tooltip=self._spot_tip(spot)))

        # Sensor nodes + collision-free labels
        placed = []                                      # occupied rectangles (x0, y0, x1, y1)

        def free(rect):
            x0, y0, x1, y1 = rect
            if x0 < 2 or y0 < 2 or x1 > w - 2 or y1 > h - 2:
                return False
            return not any(x0 < b[2] and x1 > b[0] and y0 < b[3] and y1 > b[1] for b in placed)

        nr = max(3.5, 4.2 * ms)
        nodes = []
        for zone in state["zones"]:
            zx, zy = self._pos(zone["x"], zone["y"], scale, ox, oy)
            if not visible(zx, zy, 12):
                continue
            nodes.append((zone, zx, zy))
            placed.append((zx - nr - 1, zy - nr - 1, zx + nr + 1, zy + nr + 1))
            controls.append(ft.Container(
                left=zx - nr, top=zy - nr, width=nr * 2, height=nr * 2, bgcolor=PANEL,
                border=ft.Border.all(1.6, RISK[zone["risk_level"]]), border_radius=nr))

        font = 9 + min(self.zoom, 4) * 0.5
        # Priority: burning, then major cities, then (once zoomed in) everything else by risk.
        nodes.sort(key=lambda n: (not n[0]["on_fire"], short_name(n[0]["name"]) not in LABELLED, -n[0]["risk"]))
        for zone, zx, zy in nodes:
            major = short_name(zone["name"]) in LABELLED or zone["name"] in LABELLED
            if not (major or zone["on_fire"] or self.zoom >= 1.6):
                continue
            label = zone["name"] if self.zoom >= 3.5 else short_name(zone["name"])
            lw, lh = len(label) * font * 0.56 + 6, font + 4
            for rect in (
                (zx - lw / 2, zy + nr + 2, zx + lw / 2, zy + nr + 2 + lh),     # below
                (zx - lw / 2, zy - nr - 2 - lh, zx + lw / 2, zy - nr - 2),     # above
                (zx + nr + 3, zy - lh / 2, zx + nr + 3 + lw, zy + lh / 2),     # right
                (zx - nr - 3 - lw, zy - lh / 2, zx - nr - 3, zy + lh / 2),     # left
            ):
                if free(rect):
                    placed.append(rect)
                    controls.append(ft.Container(
                        content=txt(label, font, TEXT if (major or zone["on_fire"]) else DIM,
                                    bold=major or zone["on_fire"]),
                        left=rect[0], top=rect[1], width=lw, alignment=ft.Alignment.CENTER))
                    break

        # Real place names (townships, villages, rural settlements) once you zoom in
        if self.zoom >= 4.0 and places.available():
            south, west = self.screen_to_latlon(0, h)
            north, east = self.screen_to_latlon(w, 0)
            zone_names = {short_name(z["name"]).lower() for z in state["zones"]}
            cap = 35 if self.light else 80
            pfont = 8.5 + min(self.zoom - 4.0, 3.0) * 0.3
            shown = 0
            for pl in places.in_view(south, west, north, east, limit=cap * 3):
                if shown >= cap:
                    break
                if pl["name"].lower() in zone_names:
                    continue
                qx, qy = self._pos(*project(pl["lat"], pl["lon"]), scale, ox, oy)
                if not visible(qx, qy, 4):
                    continue
                placed.append((qx - 3, qy - 3, qx + 3, qy + 3))      # the dot always shows; labels dodge it
                shown += 1
                controls.append(ft.Container(
                    left=qx - 2.5, top=qy - 2.5, width=5, height=5, bgcolor="#6B7680", border_radius=2.5,
                    tooltip=f'{pl["name"]}, {pl["province"]}\n{fmt_coord(pl["lat"], pl["lon"])}'))
                lw, lh = len(pl["name"]) * pfont * 0.56 + 6, pfont + 4
                for rect in (
                    (qx + 5, qy - lh / 2, qx + 5 + lw, qy + lh / 2),               # right
                    (qx - 5 - lw, qy - lh / 2, qx - 5, qy + lh / 2),               # left
                    (qx - lw / 2, qy + 4, qx + lw / 2, qy + 4 + lh),               # below
                ):
                    if free(rect):
                        placed.append(rect)
                        controls.append(ft.Container(
                            content=txt(pl["name"], pfont, "#4B545C"),
                            left=rect[0], top=rect[1], width=lw, alignment=ft.Alignment.CENTER))
                        break

        # Signed-in user's home marker
        home = next((z for z in state["zones"] if z["id"] == self.user_zone_id), None)
        if home:
            hx, hy = self._pos(home["x"], home["y"], scale, ox, oy)
            if visible(hx, hy):
                r = max(9, 10 * ms)
                controls.append(ft.Container(
                    left=hx - r, top=hy - r, width=r * 2, height=r * 2,
                    border=ft.Border.all(2, INFO_BLUE), border_radius=r))
                controls.append(ft.Container(
                    content=txt("You", 9, "#FFFFFF", bold=True), bgcolor=INFO_BLUE, border_radius=4,
                    padding=ft.Padding.symmetric(horizontal=5, vertical=1), left=hx - 12, top=hy - r - 17))

        # Citizen reports and the pin being placed
        for r in self.reports:
            rx, ry = self._pos(*project(r["lat"], r["lon"]), scale, ox, oy)
            if not visible(rx, ry, 16):
                continue
            size = max(20, 24 * ms)
            tip = (f'{r["kind_label"]} · {age_text(r["ts"])}' + (f'\n{r["note"]}' if r["note"] else "")
                   + f'\n{fmt_coord(r["lat"], r["lon"])}')
            controls.append(ft.Container(
                content=ft.Icon(ft.Icons.LOCATION_ON, color=INFO_BLUE, size=size),
                left=rx - size / 2, top=ry - size, width=size, height=size, tooltip=tip))
        if self.pending_pin:
            qx, qy = self._pos(*project(*self.pending_pin), scale, ox, oy)
            controls.append(ft.Container(
                content=ft.Icon(ft.Icons.PLACE, color=EMERGENCY, size=30),
                left=qx - 15, top=qy - 30, width=30, height=30))
        if self.selected:
            sel = self.selected
            sx_, sy_ = self._pos(*project(sel["lat"], sel["lon"]), scale, ox, oy)
            if visible(sx_, sy_, 16):
                controls.append(ft.Container(
                    content=ft.Icon(ft.Icons.PLACE, color="#7C3AED", size=32),
                    left=sx_ - 16, top=sy_ - 32, width=32, height=32))
            lines = [
                ft.Row([ft.Icon(ft.Icons.PLACE, color="#7C3AED", size=18),
                        ft.Container(content=txt(sel["name"], 13, TEXT, bold=True), expand=True),
                        ft.IconButton(icon=ft.Icons.CLOSE, icon_size=16, on_click=self._clear_selected)],
                       spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                txt(sel["province"], 11.5, DIM),
                txt(fmt_coord(sel["lat"], sel["lon"]), 11.5, TEXT, font_family="monospace"),
            ]
            for extra in (sel.get("note"), sel.get("sensor")):
                if extra:
                    lines.append(txt(extra, 10.5, FAINT))
            if self.on_report_here:
                lines.append(ft.TextButton(
                    "Report smoke or fire here", icon=ft.Icons.ADD_LOCATION_ALT,
                    on_click=lambda e: self.on_report_here(sel["lat"], sel["lon"])))
            controls.append(ft.Container(
                content=ft.Column(lines, spacing=1, tight=True),
                bgcolor=PANEL, border=ft.Border.all(1, LINE), border_radius=10,
                padding=ft.Padding.only(left=10, right=4, top=2, bottom=4),
                left=10, bottom=48, width=max(180, min(w - 70, 310))))
        if self.pin_mode:
            controls.append(ft.Container(
                content=ft.Row([
                    ft.Icon(ft.Icons.TOUCH_APP, color=INFO_BLUE, size=18),
                    ft.Container(content=txt("Tap the map to place your pin", 12, TEXT), expand=True),
                    ft.TextButton("Cancel", on_click=self.cancel_pin),
                ], spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                bgcolor=PANEL, border=ft.Border.all(1, INFO_BLUE), border_radius=8,
                padding=ft.Padding.symmetric(horizontal=10, vertical=2),
                left=10, top=58, width=max(160, min(w - 70, 290))))

        # Fire stations (only shown during an emergency dispatch)
        if self.dispatch:
            ox0, oy0 = self._pos(*self.dispatch["origin"], scale, ox, oy)
            controls.append(ft.Container(
                left=ox0 - 7, top=oy0 - 7, width=14, height=14, bgcolor="#FFFFFF",
                border=ft.Border.all(3, EMERGENCY), border_radius=7))
            for s in self.dispatch["stations"]:
                sx, sy = self._pos(s["x"], s["y"], scale, ox, oy)
                if not visible(sx, sy):
                    continue
                done = s["id"] in self.dispatch["done"]
                controls.append(ft.Container(
                    content=ft.Icon(ft.Icons.LOCAL_FIRE_DEPARTMENT, size=11, color="#FFFFFF"),
                    left=sx - 9, top=sy - 9, width=18, height=18, alignment=ft.Alignment.CENTER,
                    bgcolor=EMERGENCY if done else "#9AA3AB", border_radius=5,
                    border=ft.Border.all(1.5, "#FFFFFF"), tooltip=s["name"]))

        # Wind compass (bottom-right) and scale bar (bottom-left) stay fixed to the viewport.
        import math
        wx, wy = w - 38, h - 44
        controls.append(ft.Container(left=wx - 22, top=wy - 22, width=44, height=44, bgcolor=PANEL,
                                     border=ft.Border.all(1, LINE), border_radius=22))
        controls.append(ft.Container(
            content=ft.Text("➤", size=17, color=WIND), left=wx - 8, top=wy - 11,
            rotate=ft.Rotate((state["wind"]["dir"] - 90) * math.pi / 180)))
        controls.append(ft.Container(content=txt("Wind", 9.5, FAINT), left=wx - 15, top=wy + 22))

        km_per_px = KM_PER_DEG_LAT / (PX_PER_LAT * scale)
        km = next((k for k in NICE_KM if 60 <= k / km_per_px <= 150), NICE_KM[-1])
        bar_w = km / km_per_px
        controls.append(ft.Container(
            left=12, top=h - 34, width=bar_w, height=8,
            border=ft.Border(left=ft.BorderSide(1.5, DIM), right=ft.BorderSide(1.5, DIM),
                             bottom=ft.BorderSide(1.5, DIM))))
        controls.append(ft.Container(content=txt(f"{km} km", 9.5, DIM), left=12, top=h - 22))

        controls += [self.search_panel, self.results_panel, self.controls_panel]     # always on top
        self.map_stack.width, self.map_stack.height = w, h
        self.map_stack.controls = controls
