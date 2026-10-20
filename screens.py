"""
Screens added on top of the basic dialogs:

  show_safety     "What to do now" checklist, nearest hospitals and assembly points
  show_incidents  list of fires with their timelines (detected, alerts sent, status)
  show_console    station / Fire Protection Association console: SOS inbox + notices
  show_settings   alert preferences (strength, quiet hours, radius, language) and emergency contacts

Dialog helpers live in dialogs.py; it is imported lazily because dialogs.py imports this file.
"""

import asyncio
import calendar
import hmac
import time

import flet as ft

import alerts
import auth
import config
import i18n
import incidents
import nearby
import sos
from ui import (
    CONTAINED, DIM, EMERGENCY, EMERGENCY_DARK, FAINT, INFO_BLUE, LINE, RISK, TEXT, chip, fmt_coord,
    open_url, primary_button, txt,
)


def _d():
    import dialogs                      # lazy: dialogs imports this module
    return dialogs


STATUS_COLOR = {
    "new": EMERGENCY, "acknowledged": RISK["high"], "dispatched": INFO_BLUE, "resolved": RISK["low"],
    "active": EMERGENCY, "evacuation": EMERGENCY, "rescue_needed": RISK["high"], "extrication": EMERGENCY,
    "quiet": RISK["moderate"], "contained": CONTAINED, "extinguished": CONTAINED, "closed": CONTAINED,
    "cleared": CONTAINED,
}


def _status_chip(inc):
    label = (incidents.SOS_STATUS if inc.get("kind") == "sos" else incidents.FIRE_STATUS).get(inc.get("status"), inc.get("status", ""))
    return chip(label, STATUS_COLOR.get(inc.get("status"), DIM))


def _banner(text, color=EMERGENCY, icon=ft.Icons.INFO_OUTLINE):
    return ft.Container(
        content=ft.Row([ft.Icon(icon, color=color, size=18), ft.Container(content=txt(text, 12, TEXT), expand=True)],
                       spacing=8, vertical_alignment=ft.CrossAxisAlignment.START),
        border=ft.Border.all(1, color), border_radius=8, padding=10)


def _close_button(app, label="Close", on_click=None):
    return ft.TextButton(label, on_click=on_click or (lambda e: app.page.pop_dialog()))


# ---------------------------------------------------------------------------
# Safety steps, hospitals and assembly points
# ---------------------------------------------------------------------------

CHECKLISTS = {
    "veld": ("Veld or grass fire", [
        "Call 112 from a cell phone (or the local fire department) and give your exact location.",
        "Move away from the fire's path, towards bare ground, a road or ground that has already burnt. Do not run uphill: fire moves fastest uphill.",
        "Leave early if told to evacuate. Take people, medicine, phone and ID only. Do not wait to be sure.",
        "Close windows and doors. Move gas bottles, paraffin and dry material away from buildings if you can do it quickly and safely.",
        "Cover your nose and mouth with a damp cloth. Do not drive through thick smoke.",
        "If trapped in a vehicle: stay inside, park on bare ground, close windows and vents, switch on headlights.",
        "Bring animals with you if it is safe. Never go back for them once the fire has arrived.",
    ]),
    "house": ("House fire", [
        "Get everyone out and stay out. Do not go back inside for belongings.",
        "Stay low under smoke. Feel a door with the back of your hand before opening it; if it is hot, use another way out.",
        "Close doors behind you to slow the fire.",
        "Call 112 once you are outside and safe.",
        "If clothes catch fire: stop, drop and roll.",
        "Never throw water on a cooking-oil fire. Only if it is small and safe, turn off the heat and cover the pan with a lid.",
        "Electrical fire: switch off at the mains only if you can reach it safely. Never use water on it.",
        "Meet at a fixed spot outside and count everyone. Tell the fire crew if anyone is missing.",
    ]),
    "informal": ("Informal settlement fire", [
        "Shout to wake and warn your neighbours. Fire moves from shack to shack in minutes.",
        "Get children, older people and people with disabilities out first.",
        "Move to open ground away from the shacks and upwind of the smoke. Do not go back inside.",
        "Call 112 or the local fire station. Say the settlement name, the section and a landmark.",
        "Keep the access road or path clear so fire engines can reach the fire. Do not crowd it.",
        "Switch off and move paraffin stoves, gas bottles and candles away if you can do it safely; never refill a stove while it is lit.",
        "Go to the nearest agreed assembly point or community hall and register with the officials.",
    ]),
}


def _kind_for(etype):
    if etype in ("house_kitchen", "house_electrical"):
        return "house"
    return etype if etype in CHECKLISTS else "veld"


def show_safety(app, lat, lon, etype="veld"):
    """What-to-do-now checklist plus nearby hospitals and assembly points."""
    dlg_mod = _d()
    kind = {"v": _kind_for(etype)}
    body = ft.Column(spacing=10, tight=True, scroll=ft.ScrollMode.AUTO)
    where = ft.Column(spacing=6, tight=True)
    picker = ft.Dropdown(
        label="Type of fire", value=kind["v"], dense=True, border_radius=8, text_size=14,
        options=[ft.DropdownOption(key=k, text=v[0]) for k, v in CHECKLISTS.items()])

    def build():
        title, steps = CHECKLISTS[kind["v"]]
        body.controls = [
            picker, _banner("Call 112 first. This is general guidance and never replaces instructions "
                            "from fire crews, police or your municipality.", EMERGENCY, ft.Icons.WARNING_AMBER),
            txt(title, 14, TEXT, bold=True),
            *[ft.Row([ft.Icon(ft.Icons.CHECK_CIRCLE_OUTLINE, size=16, color=RISK["low"]),
                      ft.Container(content=txt(s, 12.5, TEXT), expand=True)],
                     spacing=8, vertical_alignment=ft.CrossAxisAlignment.START) for s in steps],
            ft.Divider(height=8, color=LINE),
            txt("Nearest safe places", 14, TEXT, bold=True), where,
        ]

    def change(e):
        kind["v"] = picker.value or "veld"
        build()
        app.page.update()
    picker.on_select = change

    def place_rows(title, items, what):
        rows = [txt(title, 12, DIM, bold=True)]
        if items:
            for it in items:
                rows.append(ft.Row([
                    ft.Container(content=ft.Column([txt(it["name"], 12.5, TEXT),
                                                    txt(f'{it["km"]:.1f} km · {fmt_coord(it["lat"], it["lon"])}'
                                                        + (f' · {it["phone"]}' if it.get("phone") else ""), 10.5, FAINT)],
                                                   spacing=0), expand=True),
                    ft.TextButton("Directions", icon=ft.Icons.DIRECTIONS,
                                  on_click=lambda e, it=it: open_url(app.page, nearby.directions_link(it["lat"], it["lon"])))],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER))
        else:
            rows.append(txt("None found in the map data nearby.", 11.5, FAINT))
        rows.append(ft.TextButton(f"Search for {what} on a live map", icon=ft.Icons.MAP,
                                  on_click=lambda e: open_url(app.page, nearby.map_search_link(what, lat, lon))))
        return rows

    async def load():
        where.controls = [txt("Looking up hospitals and assembly points…", 12, DIM), ft.ProgressBar()]
        app.page.update()
        data = await asyncio.to_thread(nearby.find, lat, lon)
        if data is None:
            where.controls = [
                txt("Live map data is not available here. Use these searches instead:", 12, DIM),
                ft.TextButton("Hospitals near the fire", icon=ft.Icons.LOCAL_HOSPITAL,
                              on_click=lambda e: open_url(app.page, nearby.map_search_link("hospital", lat, lon))),
                ft.TextButton("Assembly points and community halls", icon=ft.Icons.GROUPS,
                              on_click=lambda e: open_url(app.page, nearby.map_search_link("community hall", lat, lon)))]
        else:
            where.controls = [
                *place_rows("Hospitals", data["hospitals"], "hospital"),
                *place_rows("Assembly points", data["assembly"], "community hall"),
                txt("From OpenStreetMap volunteers, so it can be incomplete or out of date. Confirm with "
                    "the authorities. Official evacuation routes are announced by police and fire crews.", 10.5, FAINT)]
        app.page.update()

    build()
    dlg = dlg_mod._dialog(app, "What to do now", [body], [_close_button(app)], icon=ft.Icons.HEALTH_AND_SAFETY, width=460)
    app.page.show_dialog(dlg)
    app.page.run_task(load)


# ---------------------------------------------------------------------------
# Incidents and timelines
# ---------------------------------------------------------------------------

def show_incidents(app):
    """Recent satellite-detected fires and station notices, with a timeline for each."""
    dlg_mod = _d()
    body = ft.Column(spacing=8, tight=True, scroll=ft.ScrollMode.AUTO)

    def timeline(inc):
        rows = [txt(inc.get("title", "Incident"), 15, TEXT, bold=True), ft.Row([_status_chip(inc)]),
                txt(f'{inc.get("place", "")} · {fmt_coord(float(inc["lat"]), float(inc["lon"]))}', 11.5, DIM)]
        d = inc.get("data", {})
        if d.get("text"):
            rows.append(txt(d["text"], 12.5, TEXT))
        if inc.get("kind") == "fire":
            rows.append(txt(f'Latest: {d.get("count", 0)} hotspot(s), peak {d.get("peak", 0)}'
                            + (f', alerts sent to {d["alerts"]} nearby subscriber(s)' if d.get("alerts") else ""), 11.5, DIM))
        rows.append(ft.Divider(height=6, color=LINE))
        for ev in inc.get("events", []):
            rows.append(ft.Row([
                ft.Container(width=8, height=8, bgcolor=INFO_BLUE, border_radius=4, margin=ft.Margin.only(top=5)),
                ft.Column([txt(incidents.clock(ev["ts"]), 10.5, FAINT), txt(ev["text"], 12.5, TEXT)], spacing=0, expand=True),
            ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.START))
        if inc.get("kind") == "fire":
            rows.append(txt("Satellite data cannot confirm a fire is out. Statuses here follow new detections; "
                            "only ground crews can declare a fire contained.", 10.5, FAINT))
        return rows

    def open_one(inc):
        body.controls = timeline(inc)
        dlg.actions = [ft.TextButton("Back", on_click=lambda e: show_list()), _close_button(app)]
        app.page.update()

    def show_list(items=None):
        rows = [txt("Fires seen by NASA satellites and notices from fire stations, newest first.", 12, DIM)]
        for inc in items if items is not None else cache["rows"]:
            rows.append(ft.Container(
                content=ft.Row([
                    ft.Column([txt(inc.get("title", "Incident"), 13, TEXT, bold=True),
                               txt(incidents.clock(_epoch(inc.get("created_at"))), 10.5, FAINT)], spacing=0, expand=True),
                    _status_chip(inc)], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                border=ft.Border.all(1, LINE), border_radius=8, padding=10, ink=True,
                on_click=lambda e, inc=inc: open_one(inc)))
        if len(rows) == 1:
            rows.append(txt("No incidents recorded yet. They appear here after the server sees its first "
                            "satellite detection or a station posts a notice.", 12, DIM))
        body.controls = rows
        dlg.actions = [_close_button(app)]
        app.page.update()

    cache = {"rows": []}

    async def load():
        try:
            rows = await asyncio.to_thread(lambda: [r for r in incidents.recent(limit=80) if r.get("kind") != "sos"])
        except Exception:
            rows = []
        cache["rows"] = rows
        show_list(rows)

    body.controls = [txt("Loading…", 12, DIM), ft.ProgressBar()]
    dlg = dlg_mod._dialog(app, "Incidents and timelines", [body], [_close_button(app)], icon=ft.Icons.TIMELINE, width=460)
    app.page.show_dialog(dlg)
    if app.is_browser_build():
        body.controls = [_banner("Incident timelines need the server version of Firewatch (the Netlify page is a demo).",
                                 INFO_BLUE)]
        return
    app.page.run_task(load)


def _epoch(iso):
    try:
        return calendar.timegm(time.strptime(str(iso), "%Y-%m-%dT%H:%M:%SZ"))
    except ValueError:
        return time.time()


# ---------------------------------------------------------------------------
# Station / FPA console
# ---------------------------------------------------------------------------

_failed = {"n": 0, "until": 0.0}


def _station_label(key):
    """Station name for an access key, or None. Constant-time comparison."""
    found = None
    for k, label in config.station_logins().items():
        if hmac.compare_digest(k.encode(), (key or "").encode()):
            found = label
    return found


def show_console(app):
    dlg_mod = _d()
    if app.is_browser_build():
        app.toast("The station console needs the server version of Firewatch.")
        return
    if not config.station_logins():
        app.page.show_dialog(dlg_mod._dialog(
            app, "Station console",
            [txt("No station access key is set on this server. Set STATION_KEY (one shared key) or "
                 "STATION_KEYS (Name:key,Name:key) in the server's environment, then restart.", 12.5, TEXT)],
            [_close_button(app)], icon=ft.Icons.LOCAL_FIRE_DEPARTMENT))
        return
    if getattr(app, "station", None):
        _console(app, app.station)
        return

    key = dlg_mod._field("Station access key", ft.Icons.KEY, password=True, can_reveal_password=True, autofocus=True)
    error = dlg_mod._error_text()

    def submit(e=None):
        if time.time() < _failed["until"]:
            dlg_mod._show_error(error, "Too many wrong keys. Wait a minute and try again.")
        else:
            label = _station_label(key.value)
            if label:
                _failed["n"] = 0
                app.station = label
                app.page.pop_dialog()
                _console(app, label)
                return
            _failed["n"] += 1
            if _failed["n"] >= 5:
                _failed.update(n=0, until=time.time() + 60)
            dlg_mod._show_error(error, "That key is not recognised.")
        app.page.update()

    key.on_submit = submit
    app.page.show_dialog(dlg_mod._dialog(
        app, "Station console",
        [txt("For fire stations and Fire Protection Associations. Ask the Firewatch administrator for your key.", 12, DIM),
         key, error],
        [_close_button(app, "Cancel"), primary_button("Open console", submit, color=INFO_BLUE)],
        icon=ft.Icons.LOCAL_FIRE_DEPARTMENT))


def _console(app, label):
    dlg_mod = _d()
    alive = {"v": True}
    body = ft.Column(spacing=10, tight=True, scroll=ft.ScrollMode.AUTO)
    stamp = txt("", 10.5, FAINT)

    def close(e=None):
        alive["v"] = False
        app.page.pop_dialog()

    def sign_out(e):
        app.station = None
        close()

    async def act(inc_id, status):
        await asyncio.to_thread(incidents.set_status, inc_id, status, label)
        await load()

    def sos_card(inc):
        d, status = inc["data"], inc["status"]
        ref = inc["id"][-6:].upper()
        buttons = []
        if status == "new":
            buttons.append(primary_button("Acknowledge", lambda e: app.page.run_task(act, inc["id"], "acknowledged"),
                                          color=RISK["high"]))
        if status in ("new", "acknowledged"):
            buttons.append(primary_button("Crew dispatched", lambda e: app.page.run_task(act, inc["id"], "dispatched"),
                                          color=INFO_BLUE))
        if status in ("acknowledged", "dispatched"):
            buttons.append(primary_button("Resolved", lambda e: app.page.run_task(act, inc["id"], "resolved"),
                                          color=RISK["low"]))
        lines = [
            ft.Row([txt(f"SOS {ref}", 13, TEXT, bold=True), _status_chip(inc)], spacing=8),
            txt(f'{sos.ETYPES.get(d.get("etype"), "Fire")} near {inc.get("place", "")}', 12.5, TEXT),
        ]
        if d.get("address"):
            lines.append(txt(f'Address: {d["address"]}', 12, DIM))
        lines.append(txt(f'GPS {fmt_coord(float(inc["lat"]), float(inc["lon"]))}', 11.5, DIM, font_family="monospace"))
        if d.get("caller") or d.get("phone"):
            lines.append(txt(f'Caller: {d.get("caller", "")} {d.get("phone", "")}', 12, TEXT))
        if d.get("note"):
            lines.append(txt(f'"{d["note"]}"', 11.5, DIM))
        lines.append(txt(f'Received {incidents.clock(_epoch(inc.get("created_at")))}'
                         + (f' · acknowledged by {d["ack_by"]}' if d.get("ack_by") else "")
                         + (f' · dispatched by {d["dispatch_by"]}' if d.get("dispatch_by") else ""), 10.5, FAINT))
        links = [ft.TextButton("Open map", icon=ft.Icons.MAP,
                               on_click=lambda e: open_url(app.page, sos.maps_link(inc["lat"], inc["lon"])))]
        if d.get("phone"):
            links.append(ft.TextButton("Call caller", icon=ft.Icons.CALL,
                                       on_click=lambda e: open_url(app.page, "tel:" + str(d["phone"]))))
        lines.append(ft.Row(links, wrap=True, spacing=0))
        if buttons:
            lines.append(ft.Row(buttons, wrap=True, spacing=8, run_spacing=4))
        return ft.Container(content=ft.Column(lines, spacing=4, tight=True), border=ft.Border.all(1, LINE),
                            border_radius=8, padding=10)

    async def load():
        try:
            rows = await asyncio.to_thread(incidents.recent, "sos", 40, 48)
        except Exception as err:
            body.controls = [_banner(f"Could not read incidents: {err}")]
            app.page.update()
            return
        open_rows = [r for r in rows if r.get("status") != "resolved"]
        done = [r for r in rows if r.get("status") == "resolved"]
        cards = [sos_card(r) for r in open_rows] or [txt("No open SOS requests. New ones appear here by themselves.", 12.5, DIM)]
        if done:
            cards += [txt(f"Resolved in the last 48 hours: {len(done)}", 11.5, FAINT)]
        body.controls = [
            ft.Row([txt(f"Signed in as {label}", 12, DIM), ft.TextButton("Sign out", on_click=sign_out)],
                   alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ft.Row([primary_button("Post a notice", lambda e: show_notice_form(app, label), icon=ft.Icons.CAMPAIGN,
                                   color=INFO_BLUE),
                    ft.TextButton("Refresh", icon=ft.Icons.REFRESH, on_click=lambda e: app.page.run_task(load))],
                   wrap=True, spacing=8),
            txt("Incoming SOS requests", 14, TEXT, bold=True), *cards, stamp]
        stamp.value = "Updated " + incidents.clock(time.time()).split(" ")[-2] + " (refreshes every 10 seconds)"
        app.page.update()

    async def poll():
        while alive["v"]:
            await asyncio.sleep(10)
            if alive["v"]:
                try:
                    await load()
                except Exception:
                    break

    body.controls = [txt("Loading…", 12, DIM), ft.ProgressBar()]
    app.page.show_dialog(dlg_mod._dialog(app, "Station console", [body], [_close_button(app, "Close", close)],
                                         icon=ft.Icons.LOCAL_FIRE_DEPARTMENT, width=480))
    app.page.run_task(load)
    app.page.run_task(poll)


def show_notice_form(app, label):
    """FPA / station notice: a verified fire status or a road-rescue flag, optionally texted to people nearby."""
    dlg_mod = _d()
    kind = ft.Dropdown(label="Notice type", value="fpa", dense=True, border_radius=8, text_size=14,
                       options=[ft.DropdownOption(key="fpa", text="Fire status (FPA / station)"),
                                ft.DropdownOption(key="rescue", text="Accident and rescue (road, extrication)")])
    status = ft.Dropdown(label="Status", dense=True, border_radius=8, text_size=14)
    place_ctrls, get_place = dlg_mod._place_picker(app, label="Place (required)")
    text = ft.TextField(label="Message (max 160 characters)", multiline=True, min_lines=2, max_lines=3, max_length=160,
                        border_radius=8, text_size=14)
    radius = ft.Dropdown(label="Message people within", value="15", dense=True, border_radius=8, text_size=14,
                         options=[ft.DropdownOption(key=str(k), text=f"{k} km") for k in (5, 10, 15, 25, 50)])
    send = ft.Checkbox(label="Also send SMS / email to subscribers inside this radius", value=False)
    error = dlg_mod._error_text()
    result = txt("", 12, TEXT)

    def fill_status():
        opts = incidents.FPA_STATUS if kind.value == "fpa" else incidents.RESCUE_STATUS
        status.options = [ft.DropdownOption(key=k, text=v) for k, v in opts.items()]
        status.value = next(iter(opts))
        radius.visible = send.visible = kind.value == "fpa"

    def change(e):
        fill_status()
        app.page.update()
    kind.on_select = change
    fill_status()

    async def post():
        place = get_place()
        if not place:
            dlg_mod._show_error(error, "Search for and choose the place this notice is about.")
            app.page.update()
            return
        if not (text.value or "").strip():
            dlg_mod._show_error(error, "Write the message people should read.")
            app.page.update()
            return
        dlg_mod._show_error(error, "")
        post_button.disabled = True
        result.value = "Saving…"
        app.page.update()
        where = f'{place["name"]}, {place["province"]}'
        msg = (text.value or "").strip()
        inc = await asyncio.to_thread(incidents.post_notice, kind.value, status.value, where, place["lat"], place["lon"],
                                      msg, label, int(radius.value or 0) if send.value else 0)
        note = f"Notice saved ({inc['id'][-6:].upper()}) and shown on the map."
        if send.value and kind.value == "fpa":
            sms_text = f"Firewatch {incidents.FPA_STATUS.get(status.value, '')}: {where}. {msg}"[:300]
            n, errs = await asyncio.to_thread(alerts.broadcast, place["lat"], place["lon"], int(radius.value or 15), sms_text)
            note += f" Messaged {n} subscriber(s)." + (" Problems: " + "; ".join(errs) if errs else "")
            await asyncio.to_thread(_log_broadcast, inc["id"], n, errs)
        result.value = note
        app.refresh_notices()
        post_button.disabled = False
        app.page.update()

    post_button = primary_button("Post notice", lambda e: app.page.run_task(post), icon=ft.Icons.CAMPAIGN, color=INFO_BLUE)
    app.page.show_dialog(dlg_mod._dialog(
        app, "Post a notice",
        [txt("Only post what you have confirmed on the ground. Notices show on the public map.", 12, DIM),
         kind, status, *place_ctrls, text, radius, send, error, result],
        [_close_button(app), post_button], icon=ft.Icons.CAMPAIGN, width=440))


def _log_broadcast(incident_id, n, errs):
    inc = incidents.get(incident_id)
    if inc:
        incidents.event(inc, f"Messaged {n} subscriber(s) nearby" + (f" ({len(errs)} problem(s))" if errs else ""))
        incidents.save(inc)


# ---------------------------------------------------------------------------
# Alert settings and emergency contacts
# ---------------------------------------------------------------------------

def show_settings(app):
    dlg_mod = _d()
    user = app.user
    if not user:
        app.toast("Log in to change your alert settings.")
        return
    lang = ft.Dropdown(label="Language for alerts and SOS", value=i18n.lang_ok(user.get("lang", "en")), dense=True,
                       border_radius=8, text_size=14,
                       options=[ft.DropdownOption(key=k, text=v) for k, v in i18n.LANGS.items()])
    sev = ft.Dropdown(label="Alert me about", value=user.get("min_sev", "low"), dense=True, border_radius=8, text_size=14,
                      options=[ft.DropdownOption(key=k, text=t) for k, t in alerts.MIN_SEV_OPTIONS])
    radius_val = str(int(user.get("radius_km") or config.ALERT_RADIUS_KM))
    radius_opts = sorted({10, 20, 30, 50, 75, 100, int(radius_val)})
    radius = ft.Dropdown(label="Distance from my place", value=radius_val, dense=True, border_radius=8, text_size=14,
                         options=[ft.DropdownOption(key=str(k), text=f"{k} km") for k in radius_opts])
    quiet = user.get("quiet")
    quiet_on = ft.Switch(label="Quiet hours (strong fires still get through)", value=bool(quiet))
    hours = [ft.DropdownOption(key=str(h), text=f"{h:02d}:00") for h in range(24)]
    q_from = ft.Dropdown(label="From", value=str(quiet[0] if quiet else 22), width=120, dense=True, border_radius=8,
                         text_size=14, options=hours)
    q_to = ft.Dropdown(label="Until", value=str(quiet[1] if quiet else 6), width=120, dense=True, border_radius=8,
                       text_size=14, options=hours)
    contacts = list(user.get("contacts") or [])
    rows = []
    for i in range(auth.MAX_CONTACTS):
        c = contacts[i] if i < len(contacts) else {"name": "", "phone": ""}
        rows.append((dlg_mod._field(f"Contact {i + 1} name", ft.Icons.PERSON, value=c.get("name", "")),
                     dlg_mod._field("Mobile number", ft.Icons.PHONE, value=c.get("phone", ""), hint_text="082 123 4567")))
    error = dlg_mod._error_text()
    history = ft.Column(spacing=2, tight=True)

    def save(e=None):
        updated, err = auth.update_settings(
            user["email"], lang=lang.value, min_sev=sev.value,
            quiet=[int(q_from.value), int(q_to.value)] if quiet_on.value else None,
            radius_km=int(radius.value or 30),
            contacts=[{"name": n.value, "phone": p.value} for n, p in rows])
        if err:
            dlg_mod._show_error(error, err)
            app.page.update()
            return
        app.page.pop_dialog()
        app.set_user(updated)
        app.toast("Settings saved.")

    async def load_history():
        if app.is_browser_build():
            return
        rows_ = await asyncio.to_thread(alerts.history_for, user["email"], 8)
        if rows_:
            history.controls = [txt("Recent messages from Firewatch", 12, DIM, bold=True)] + [
                txt(f'{(r.get("created_at") or "")[:16].replace("T", " ")} UTC · {r.get("channels", "")} · '
                    f'{r.get("place", "")}' + (f' · {r["km"]} km' if r.get("km") is not None else ""), 11, FAINT)
                for r in rows_]
            app.page.update()

    ctrls = [lang, sev, radius, quiet_on, ft.Row([q_from, q_to], spacing=10),
             ft.Divider(height=8, color=LINE),
             txt("Emergency contacts", 13, TEXT, bold=True),
             txt("When you press SOS, these people get an SMS with your place and number. Up to three. "
                 "Only add people who agreed.", 11.5, DIM)]
    for n, p in rows:
        ctrls += [n, p]
    ctrls += [error, history]
    app.page.show_dialog(dlg_mod._dialog(
        app, "Alert settings and emergency contacts", ctrls,
        [_close_button(app, "Cancel"), primary_button("Save", save, color=INFO_BLUE)],
        icon=ft.Icons.TUNE, width=440))
    app.page.run_task(load_history)
