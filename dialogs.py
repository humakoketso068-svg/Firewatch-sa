"""Dialogs: sign up, log in, profile, and the emergency fire-station alert."""

import asyncio
import random

import flet as ft

import auth
import i18n
import incidents
import places
import reports
import screens
import sos
from stations import distance_km, nearby_stations
from ui import (
    DIM, EMERGENCY, EMERGENCY_DARK, FAINT, INFO_BLUE, RISK, TEXT, open_url,
    fmt_coord, primary_button, txt,
)


def _field(label, icon, **kw):
    return ft.TextField(label=label, prefix_icon=icon, dense=True, border_radius=8, text_size=14, **kw)


def _width(app, wanted):
    """Dialog width that never exceeds the screen (phones are ~360 px wide)."""
    page_w = getattr(app.page, "width", None) or 1000
    return max(240, min(wanted, page_w - 72))


def _zone_dropdown(app, label="Nearest town", value=None, width=None):
    zones = sorted(app.sim.zones, key=lambda z: (z["province"], z["name"]))
    return ft.Dropdown(
        label=label, value=value, width=width, dense=True, border_radius=8, text_size=14,
        editable=True, enable_filter=True, menu_height=300, leading_icon=ft.Icons.LOCATION_ON,
        options=[ft.DropdownOption(key=z["id"], text=f'{z["name"].split(" (")[0]}, {z["province"]}') for z in zones],
    )


def _place_picker(app, current=None, label="Exact town or village for alerts (optional)"):
    """Optional exact town/village search. Returns (controls, get_place)."""
    chosen = {"place": current}
    field = ft.TextField(label=label, dense=True, border_radius=8,
                         text_size=14, prefix_icon=ft.Icons.PIN_DROP,
                         value=(f'{current["name"]}, {current["province"]}' if current else ""),
                         hint_text="Type a name, e.g. Lerome")
    results = ft.Column(spacing=0, tight=True)
    status = txt("", 11.5, DIM)
    status.value = (f'Alerts use {fmt_coord(current["lat"], current["lon"])}' if current else
                    ("" if places.available() else "Place list not built yet (run build_places.py)."))

    def pick(p):
        chosen["place"] = p
        field.value = f'{p["name"]}, {p["province"]}'
        status.value = f'Alerts use {fmt_coord(p["lat"], p["lon"])}'
        results.controls = []
        app.page.update()

    def on_change(e):
        q = (field.value or "").strip()
        if not q:
            chosen["place"], status.value = None, ""
        found = places.search(q, 5) if len(q) >= 2 else []
        results.controls = [
            ft.TextButton(f'{p["name"]}, {p["province"]}', icon=ft.Icons.LOCATION_ON,
                          on_click=lambda e, p=p: pick(p)) for p in found]
        app.page.update()

    field.on_change = on_change
    return [field, results, status], (lambda: chosen["place"])


ALERT_OPTIONS = [("off", "Off"), ("email", "Email"), ("sms", "SMS (text message)"), ("both", "Email and SMS")]


def _alerts_dropdown(value="off"):
    return ft.Dropdown(
        label="Fire alerts for my town", value=value or "off", dense=True, border_radius=8, text_size=14,
        leading_icon=ft.Icons.NOTIFICATIONS_ACTIVE,
        options=[ft.DropdownOption(key=k, text=t) for k, t in ALERT_OPTIONS],
    )


ALERT_NOTE = ("Alerts store your email, number and town on our server so we can message you "
              "when a satellite sees a fire near your town. Choose Off any time.")


def _error_text():
    return ft.Text("", color=EMERGENCY, size=12.5, visible=False)


def _show_error(label, message):
    label.value, label.visible = message, bool(message)


def _dialog(app, title, body, actions, icon=ft.Icons.LOCAL_FIRE_DEPARTMENT, width=400):
    return ft.AlertDialog(
        modal=True,
        shape=ft.RoundedRectangleBorder(radius=14),
        title=ft.Row([ft.Icon(icon, color=EMERGENCY, size=22), txt(title, 18, TEXT, bold=True)], spacing=8),
        content=ft.Container(content=ft.Column(body, spacing=12, tight=True, scroll=ft.ScrollMode.AUTO), width=_width(app, width)),
        actions=actions, actions_alignment=ft.MainAxisAlignment.END,
    )


# ---------------------------------------------------------------------------
# Sign up / log in / profile
# ---------------------------------------------------------------------------

def show_login(app):
    email = _field("Email", ft.Icons.EMAIL, autofocus=True)
    password = _field("Password", ft.Icons.LOCK, password=True, can_reveal_password=True)
    keep = ft.Checkbox(label="Keep me signed in on this device", value=True)
    error = _error_text()

    def submit(e=None):
        user, err = auth.login(email.value, password.value)
        if err:
            _show_error(error, err)
            app.page.update()
            return
        app.page.pop_dialog()
        app.keep_signed_in = bool(keep.value)
        app.set_user(user)

    password.on_submit = submit
    email.on_submit = submit
    dlg = _dialog(
        app, "Log in to Firewatch",
        [txt("Welcome back. Log in to send emergency alerts with your details attached.", 12.5, DIM),
         email, password, keep, error,
         ft.TextButton("New here? Create an account", on_click=lambda e: (app.page.pop_dialog(), show_signup(app)))],
        [ft.TextButton("Cancel", on_click=lambda e: app.page.pop_dialog()),
         primary_button("Log in", submit)],
    )
    app.page.show_dialog(dlg)


def show_signup(app):
    name = _field("Full name", ft.Icons.PERSON, autofocus=True)
    email = _field("Email", ft.Icons.EMAIL)
    phone = _field("Mobile number", ft.Icons.PHONE, hint_text="082 123 4567")
    town = _zone_dropdown(app)
    alerts = _alerts_dropdown("off")
    place_ctrls, get_place = _place_picker(app)
    password = _field("Password (min. 8 characters)", ft.Icons.LOCK, password=True, can_reveal_password=True)
    confirm = _field("Confirm password", ft.Icons.LOCK, password=True, can_reveal_password=True)
    consent = ft.Checkbox(
        label="I agree that my name, mobile number and location are shared with fire "
              "stations when I send an emergency alert.",
        value=False,
    )
    error = _error_text()

    def submit(e=None):
        if password.value != confirm.value:
            _show_error(error, "Passwords do not match.")
            app.page.update()
            return
        user, err = auth.register(name.value, email.value, phone.value, town.value, password.value, consent.value,
                                  alerts.value or "off", get_place())
        if err:
            _show_error(error, err)
            app.page.update()
            return
        app.page.pop_dialog()
        app.keep_signed_in = True
        app.set_user(user)
        app.toast(f"Welcome, {user['name'].split()[0]}. Your account is ready.")

    confirm.on_submit = submit
    dlg = _dialog(
        app, "Create your account",
        [txt("Your details let fire stations reach you and show you alerts for your area.", 12.5, DIM),
         name, email, phone, town, alerts, *place_ctrls, txt(ALERT_NOTE, 11, FAINT), password, confirm, consent, error,
         ft.TextButton("Already have an account? Log in", on_click=lambda e: (app.page.pop_dialog(), show_login(app)))],
        [ft.TextButton("Cancel", on_click=lambda e: app.page.pop_dialog()),
         primary_button("Create account", submit)],
        width=420,
    )
    app.page.show_dialog(dlg)


def show_profile(app):
    user = app.user
    name = _field("Full name", ft.Icons.PERSON, value=user["name"])
    phone = _field("Mobile number", ft.Icons.PHONE, value=user["phone"])
    town = _zone_dropdown(app, value=user["home_zone_id"])
    alerts = _alerts_dropdown(user.get("alerts", "off"))
    place_ctrls, get_place = _place_picker(app, user.get("alert_place"))
    info = txt("", 12, DIM)
    info.visible = False
    error = _error_text()

    def save(e=None):
        updated, err = auth.update_profile(user["email"], name.value, phone.value, town.value, alerts.value or "off",
                                            get_place())
        if err:
            _show_error(error, err)
            app.page.update()
            return
        app.page.pop_dialog()
        app.set_user(updated)
        app.toast("Profile updated.")

    async def run_test():
        info.value, info.visible = "Sending a test alert…", True
        app.page.update()
        import alerts as alert_service
        message = await asyncio.to_thread(alert_service.send_test, dict(app.user))
        info.value = message
        app.page.update()

    def test_alert(e=None):
        if app.is_browser_build():
            info.value, info.visible = "Alerts need the server version of Firewatch.", True
            app.page.update()
            return
        app.page.run_task(run_test)

    def sign_out(e):
        app.page.pop_dialog()
        app.set_user(None)
        app.toast("You have been logged out.")

    dlg = _dialog(
        app, "Your profile",
        [txt(user["email"], 12.5, DIM), name, phone, town, alerts, *place_ctrls, txt(ALERT_NOTE, 11, FAINT),
         ft.TextButton("Send me a test alert", icon=ft.Icons.SEND, on_click=test_alert),
         ft.TextButton("Alert settings and emergency contacts", icon=ft.Icons.TUNE,
                       on_click=lambda e: (app.page.pop_dialog(), screens.show_settings(app))), info, error],
        [ft.TextButton("Log out", on_click=sign_out, style=ft.ButtonStyle(color=EMERGENCY)),
         ft.TextButton("Cancel", on_click=lambda e: app.page.pop_dialog()),
         primary_button("Save", save, color=INFO_BLUE)],
        icon=ft.Icons.ACCOUNT_CIRCLE,
    )
    app.page.show_dialog(dlg)


# ---------------------------------------------------------------------------
# Emergency alert
# ---------------------------------------------------------------------------

def show_emergency(app):
    user = app.user
    state = app.sim.snapshot()
    active = [f for f in state["fires"] if not f["contained"]]
    if user:
        default = user["home_zone_id"]
    elif active:
        default = active[0]["zone_id"]
    else:
        default = state["top_zone_id"]

    lang = {"v": (user or {}).get("lang", "en")}
    real = not app.is_browser_build()
    L = lambda key: i18n.t(lang["v"], key)

    body = ft.Column(spacing=12, tight=True, scroll=ft.ScrollMode.AUTO)
    actions = ft.Row(alignment=ft.MainAxisAlignment.END, spacing=8, wrap=True, run_spacing=4)
    title = txt("", 19, EMERGENCY_DARK, bold=True)
    error = _error_text()

    def banner(text, color=EMERGENCY, icon=ft.Icons.WARNING_AMBER):
        return ft.Container(
            content=ft.Row([ft.Icon(icon, color=color, size=20),
                            ft.Container(content=txt(text, 12.5, TEXT), expand=True)], spacing=10),
            bgcolor="#FDF0EE" if color == EMERGENCY else "#EEF7F1",
            border=ft.Border.all(1, color), border_radius=8, padding=10,
        )

    def call_112(e=None):
        open_url(app.page, "tel:112")

    def build_form():
        title.value = L("sos_title")
        town = _zone_dropdown(app, L("sos_where"), form.get("town", default))
        town.on_select = lambda e: form.update(town=town.value)
        etype = ft.Dropdown(
            label=L("sos_type"), value=form.get("etype", "veld"), dense=True, border_radius=8, text_size=14,
            leading_icon=ft.Icons.LOCAL_FIRE_DEPARTMENT,
            options=[ft.DropdownOption(key=k, text=v) for k, v in sos.ETYPES.items()])
        etype.on_select = lambda e: form.update(etype=etype.value)
        address = _field(L("sos_address"), ft.Icons.HOME, value=form.get("address", ""))
        details = ft.TextField(label=L("sos_what"), multiline=True, min_lines=2, max_lines=3, border_radius=8,
                               text_size=14, value=form.get("details", ""))
        name = _field(L("sos_name"), ft.Icons.PERSON, value=user["name"] if user else form.get("name", ""))
        phone = _field(L("sos_phone"), ft.Icons.PHONE, value=user["phone"] if user else form.get("phone", ""))
        lang_dd = ft.Dropdown(
            label="Language", value=lang["v"], dense=True, border_radius=8, text_size=13, width=170,
            options=[ft.DropdownOption(key=k, text=v) for k, v in i18n.LANGS.items()])

        def change_lang(e):
            form.update(town=town.value, etype=etype.value, address=address.value, details=details.value,
                        name=name.value, phone=phone.value)
            lang["v"] = lang_dd.value or "en"
            build_form()
            app.page.update()
        lang_dd.on_select = change_lang
        picker, get_place = _place_picker(app, form.get("place"), label="Exact place (optional)")
        who = ([txt(f"{user['name']}, {user['phone']}", 12, DIM)] if user
               else [name, phone, txt("Tip: sign up so this is filled in automatically.", 11.5, FAINT)])
        note = ("Station crews that use Firewatch see this at once, and confirmed stations are messaged by SMS. "
                "Always also call 112."
                if real else
                "Demo only: this web version cannot send real messages. In a real emergency dial 112.")

        def start(e=None):
            form.update(town=town.value, etype=etype.value, address=address.value, details=details.value,
                        name=name.value, phone=phone.value, place=get_place())
            who_name = user["name"] if user else (name.value or "").strip()
            who_phone = user["phone"] if user else auth.clean_phone(phone.value)
            if not town.value:
                _show_error(error, L("sos_where"))
            elif not user and (len(who_name) < 2 or not auth.valid_phone(who_phone)):
                _show_error(error, "Enter your name and a valid mobile number so crews can call you back.")
            else:
                zone = next(z for z in app.sim.zones if z["id"] == town.value)
                chosen = get_place()
                if chosen:
                    lat, lon = chosen["lat"], chosen["lon"]
                    place = f'{chosen["name"]}, {chosen["province"]}'
                else:
                    lat, lon, place = zone["lat"], zone["lon"], zone["name"].split(" (")[0] + ", " + zone["province"]
                args = dict(zone=zone, lat=lat, lon=lon, place=place, who=who_name, phone=who_phone,
                            etype=etype.value or "veld", address=(address.value or "").strip(),
                            note=(details.value or "").strip())
                app.page.run_task(run_real if real else run_demo, args)
                return
            app.page.update()

        body.controls = [lang_dd, banner(L("sos_warn")), town, picker[0], picker[1], picker[2], etype, address,
                         details, *who, error, txt(note, 11.5, FAINT)]
        actions.controls = [
            ft.TextButton(L("cancel"), on_click=lambda e: app.page.pop_dialog()),
            ft.TextButton("Call 112", icon=ft.Icons.CALL, on_click=call_112),
            primary_button(L("sos_send"), start, icon=ft.Icons.SOS),
        ]

    form = {}

    async def run_real(a):
        body.controls = [txt(L("sos_sending"), 13, TEXT, bold=True), ft.ProgressBar(color=EMERGENCY)]
        actions.controls = [ft.TextButton("Call 112", icon=ft.Icons.CALL, on_click=call_112)]
        app.map.focus_on(a["zone"]["x"], a["zone"]["y"], 3.0)
        app.page.update()
        contacts = (user or {}).get("contacts", [])
        try:
            inc = await asyncio.to_thread(
                sos.trigger, a["lat"], a["lon"], a["place"], a["who"], a["phone"], a["etype"], a["address"],
                a["note"], lang["v"], contacts, (user or {}).get("email", ""))
        except Exception as err:
            body.controls = [banner(f"Could not record the alert ({err}). Call 112 now.")]
            actions.controls = [ft.TextButton("Call 112", icon=ft.Icons.CALL, on_click=call_112),
                                primary_button(L("done"), lambda e: app.page.pop_dialog(), color=INFO_BLUE)]
            app.page.update()
            return
        app.sim.log_event("extreme", "Emergency", f"SOS from [b]{a['place']}[/b] (ref {inc['id'][-6:].upper()}).")
        rows = []
        for d in inc["data"]["deliveries"]:
            when = incidents.clock(d["at"]).split(" SAST")[0].split(" ")[-1]
            ok = d["ok"]
            rows.append(ft.Row([
                ft.Icon(ft.Icons.CHECK_CIRCLE if ok else ft.Icons.ERROR_OUTLINE, size=18,
                        color=RISK["low"] if ok else EMERGENCY),
                ft.Column([txt(d["to"], 13, TEXT),
                           txt((f"Sent by {d['via']} at {when} (accepted by the provider)" if ok else d["error"]), 11, DIM)],
                          spacing=0, expand=True)], vertical_alignment=ft.CrossAxisAlignment.START))
        status = txt("Waiting for a fire station to acknowledge…", 12, DIM)
        if not rows:
            rows.append(banner("No fire station near you can be messaged directly yet. Call 112 now. "
                               "Station crews who use the Firewatch console can still see this alert."))
        body.controls = [
            txt(f"Reference {inc['id'][-6:].upper()}", 13, TEXT, bold=True), *rows, status,
            banner(L("sos_call")),
        ]
        actions.controls = [
            ft.TextButton("Call 112", icon=ft.Icons.CALL, on_click=call_112),
            ft.TextButton("Safety steps", icon=ft.Icons.HEALTH_AND_SAFETY,
                          on_click=lambda e: screens.show_safety(app, a["lat"], a["lon"], a["etype"])),
            primary_button(L("done"), lambda e: app.page.pop_dialog(), color=INFO_BLUE),
        ]
        app.page.update()
        for _ in range(30):                              # watch for up to ~3 minutes
            await asyncio.sleep(6)
            cur = await asyncio.to_thread(incidents.get, inc["id"])
            if not cur:
                break
            if cur["status"] in ("acknowledged", "dispatched", "resolved"):
                by = cur["data"].get("dispatch_by") or cur["data"].get("ack_by") or "A fire station"
                status.value = f"{incidents.SOS_STATUS[cur['status']]} by {by}"
                status.color = RISK["low"]
                app.page.update()
                if cur["status"] != "acknowledged":
                    break

    async def run_demo(a):
        chosen = nearby_stations(a["lat"], a["lon"])
        ref = f"DEMO-{random.randint(1000, 9999)}"
        body.controls = [txt("Demo: no real messages are sent in this web version.", 12.5, EMERGENCY, bold=True)] + [
            txt(f"{s['name']} · {km:.0f} km", 12.5, TEXT) for s, km in chosen]
        actions.controls = [ft.TextButton("Call 112", icon=ft.Icons.CALL, on_click=call_112),
                            primary_button(L("done"), lambda e: app.page.pop_dialog(), color=INFO_BLUE)]
        app.map.dispatch = {"origin": (a["zone"]["x"], a["zone"]["y"]), "stations": [s for s, _ in chosen],
                            "done": {s["id"] for s, _ in chosen}}
        app.map.focus_on(a["zone"]["x"], a["zone"]["y"], 3.0)
        app.sim.log_event("extreme", "Emergency", f"Demo alert from [b]{a['place']}[/b] (ref {ref}).")
        app._redraw_map()
        app.page.update()

    build_form()
    dlg = ft.AlertDialog(
        modal=True, shape=ft.RoundedRectangleBorder(radius=14),
        title=ft.Row([ft.Icon(ft.Icons.SOS, color=EMERGENCY, size=26), title], spacing=8),
        content=ft.Container(content=body, width=_width(app, 440)),
        actions=[actions],
    )
    app.page.show_dialog(dlg)


# ---------------------------------------------------------------------------
# Citizen report
# ---------------------------------------------------------------------------

def show_report(app, lat, lon):
    user = app.user
    near = min(app.sim.zones, key=lambda z: distance_km(lat, lon, z["lat"], z["lon"]))
    km = distance_km(lat, lon, near["lat"], near["lon"])
    spot, spot_km = places.nearest(lat, lon, 30)
    if spot:
        where = f"Near {spot['name']}, {spot['province']} ({spot_km:.0f} km away)"
    else:
        where = f"About {km:.0f} km from {near['name'].split(' (')[0]}, {near['province']}"
    kind = ft.Dropdown(
        label="What can you see?", value="smoke", dense=True, border_radius=8, text_size=14,
        options=[ft.DropdownOption(key=k, text=v) for k, v in reports.KINDS.items()],
    )
    note = ft.TextField(
        label="Details (optional)", multiline=True, min_lines=2, max_lines=3, max_length=reports.MAX_NOTE,
        border_radius=8, text_size=14, hint_text="e.g. Thick smoke on the hill, blowing towards the farms",
    )
    address = _field("Street address (for house fires)", ft.Icons.HOME, max_length=reports.MAX_ADDRESS)
    error = _error_text()

    def close(e=None):
        app.map.pending_pin = None
        app._redraw_map()
        app.page.pop_dialog()

    async def send():
        send_button.disabled = True
        app.page.update()
        row, err = await asyncio.to_thread(reports.add_report, user, lat, lon, kind.value, note.value, address.value)
        if err:
            _show_error(error, err)
            send_button.disabled = False
            app.page.update()
            return
        close()
        await app.pull_reports_now()
        app.toast("Thank you. Your report is on the map for 24 hours. In an emergency, dial 112.")

    send_button = primary_button("Send report", lambda e: app.page.run_task(send), color=INFO_BLUE)
    dlg = _dialog(
        app, "Report smoke or fire",
        [txt(where, 12.5, DIM), txt(fmt_coord(lat, lon), 12, TEXT, font_family="monospace"),
         kind, address, note, error,
         txt("Reports are public, show your first name and start unverified: they are marked verified when "
             "a NASA hotspot is nearby or other people confirm them. This does not alert "
             "fire crews. In an emergency use the SOS button or call 112.", 11, FAINT)],
        [ft.TextButton("Cancel", on_click=close), send_button],
        icon=ft.Icons.ADD_LOCATION_ALT,
    )
    app.page.show_dialog(dlg)


def show_report_detail(app, r):
    """Tap on a report marker: details, how it was verified, and 'I can see this too'."""
    level = r.get("verified", "unverified")
    info = txt("", 12, DIM)
    mine = bool(app.user) and r.get("rid") == reports.reporter_id(app.user["email"])

    async def confirm():
        button.disabled = True
        app.page.update()
        votes, err = await asyncio.to_thread(reports.vote, r["id"], app.user)
        info.value = err or f"Thank you. {votes} confirmation(s) now."
        info.color = EMERGENCY if err else RISK["low"]
        button.disabled = False
        if not err:
            await app.pull_reports_now()
        app.page.update()

    def on_confirm(e):
        if not app.user:
            app.page.pop_dialog()
            show_login(app)
        else:
            app.page.run_task(confirm)

    button = primary_button("I can see this too", on_confirm, icon=ft.Icons.THUMB_UP, color=INFO_BLUE)
    button.visible = not mine
    spot, spot_km = places.nearest(r["lat"], r["lon"], 30)
    where = f"Near {spot['name']}, {spot['province']} ({spot_km:.0f} km away)" if spot else ""
    dlg = _dialog(
        app, r["kind_label"],
        [txt(f'{where}' if where else fmt_coord(r["lat"], r["lon"]), 12.5, DIM),
         txt(fmt_coord(r["lat"], r["lon"]), 12, TEXT, font_family="monospace"),
         txt(f'Reported {incidents.clock(r["ts"])} by {r.get("reporter") or "a user"}', 12, DIM),
         *( [txt(r["note"], 13, TEXT)] if r.get("note") else [] ),
         ft.Row([ft.Icon(ft.Icons.VERIFIED if level != "unverified" else ft.Icons.HELP_OUTLINE, size=18,
                         color=RISK["low"] if level != "unverified" else FAINT),
                 txt(reports.VERIFY_LABEL.get(level, ""), 12.5, TEXT)], spacing=6),
         txt(f'{r.get("votes", 0)} confirmation(s) from other people', 12, DIM), info,
         txt("Not a substitute for an alert to fire crews. In an emergency use SOS or call 112.", 11, FAINT)],
        [ft.TextButton("Close", on_click=lambda e: app.page.pop_dialog()), button],
        icon=ft.Icons.LOCATION_ON)
    app.page.show_dialog(dlg)
