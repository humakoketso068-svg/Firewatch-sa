"""Dialogs: sign up, log in, profile, and the emergency fire-station alert."""

import asyncio
import random

import flet as ft

import auth
import places
import reports
from stations import distance_km, eta_minutes, nearby_stations
from ui import (
    DIM, EMERGENCY, EMERGENCY_DARK, FAINT, INFO_BLUE, LINE, LINE_SOFT, RISK, TEXT,
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


def _place_picker(app, current=None):
    """Optional exact town/village search. Returns (controls, get_place)."""
    chosen = {"place": current}
    field = ft.TextField(label="Exact town or village for alerts (optional)", dense=True, border_radius=8,
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
    error = _error_text()

    def submit(e=None):
        user, err = auth.login(email.value, password.value)
        if err:
            _show_error(error, err)
            app.page.update()
            return
        app.page.pop_dialog()
        app.set_user(user)

    password.on_submit = submit
    email.on_submit = submit
    dlg = _dialog(
        app, "Log in to Firewatch",
        [txt("Welcome back. Log in to send emergency alerts with your details attached.", 12.5, DIM),
         email, password, error,
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
         ft.TextButton("Send me a test alert", icon=ft.Icons.SEND, on_click=test_alert), info, error],
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

    town = _zone_dropdown(app, "Where is the emergency?", default)
    details = ft.TextField(
        label="What is happening? (optional)", multiline=True, min_lines=2, max_lines=3,
        border_radius=8, text_size=14, hint_text="e.g. Veld fire moving towards houses",
    )
    name = _field("Your name", ft.Icons.PERSON, value=user["name"] if user else "")
    phone = _field("Mobile number (for call-back)", ft.Icons.PHONE, value=user["phone"] if user else "")
    error = _error_text()
    body = ft.Column(spacing=12, tight=True, scroll=ft.ScrollMode.AUTO)
    actions = ft.Row(alignment=ft.MainAxisAlignment.END, spacing=8, wrap=True, run_spacing=4)

    def banner(text, color=EMERGENCY, icon=ft.Icons.WARNING_AMBER):
        return ft.Container(
            content=ft.Row([ft.Icon(icon, color=color, size=20),
                            ft.Container(content=txt(text, 12.5, TEXT), expand=True)], spacing=10),
            bgcolor="#FDF0EE" if color == EMERGENCY else "#EEF7F1",
            border=ft.Border.all(1, color), border_radius=8, padding=10,
        )

    def build_form():
        who = ([txt(f"Alert will include: {user['name']}, {user['phone']}", 12, DIM)] if user
               else [name, phone, txt("Tip: sign up so this is filled in automatically.", 11.5, FAINT)])
        body.controls = [
            banner("This will alert every fire station near the location below. "
                   "Use it for a real fire threatening people or property."),
            town, details, *who, error,
            txt("Demo only: no real calls or messages are sent. In a real emergency, dial 112 "
                "from a cell phone or call your local fire department.", 11.5, FAINT),
        ]
        actions.controls = [
            ft.TextButton("Cancel", on_click=lambda e: app.page.pop_dialog()),
            primary_button("Alert fire stations", start, icon=ft.Icons.SOS),
        ]

    def start(e=None):
        who_name = user["name"] if user else (name.value or "").strip()
        who_phone = user["phone"] if user else auth.clean_phone(phone.value)
        if not town.value:
            _show_error(error, "Choose where the emergency is.")
        elif not user and (len(who_name) < 2 or not auth.valid_phone(who_phone)):
            _show_error(error, "Enter your name and a valid mobile number so crews can call you back.")
        else:
            zone = next(z for z in app.sim.zones if z["id"] == town.value)
            app.page.run_task(dispatch, zone, who_name, who_phone, (details.value or "").strip())
            return
        app.page.update()

    async def dispatch(zone, who_name, who_phone, note):
        chosen = nearby_stations(zone["lat"], zone["lon"])
        ref = f"FW-{random.randint(100000, 999999)}"
        rows = {}
        for s, km in chosen:
            status = txt("Waiting…", 11.5, FAINT)
            icon = ft.Icon(ft.Icons.RADIO_BUTTON_UNCHECKED, size=18, color=FAINT)
            rows[s["id"]] = (icon, status)
        header = txt(f"Contacting {len(chosen)} fire stations near {zone['name'].split(' (')[0]}…", 13, TEXT, bold=True)
        body.controls = [header] + [
            ft.Container(
                content=ft.Row([
                    rows[s["id"]][0],
                    ft.Column([txt(s["name"], 13, TEXT), txt(f"{km:.0f} km away", 11, DIM)], spacing=0, expand=True),
                    rows[s["id"]][1]], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                padding=ft.Padding.symmetric(vertical=7), border=ft.Border.only(bottom=ft.BorderSide(1, LINE_SOFT)))
            for s, km in chosen
        ]
        actions.controls = [ft.ProgressRing(width=18, height=18, stroke_width=2.5, color=EMERGENCY)]
        app.map.dispatch = {"origin": (zone["x"], zone["y"]), "stations": [s for s, _ in chosen], "done": set()}
        app.map.focus_on(zone["x"], zone["y"], 3.0)
        app.page.update()

        for s, km in chosen:
            icon, status = rows[s["id"]]
            status.value, status.color = "Contacting…", INFO_BLUE
            app.page.update()
            await asyncio.sleep(random.uniform(0.35, 0.7))
            icon.icon, icon.color = ft.Icons.CHECK_CIRCLE, RISK["low"]
            status.value, status.color = f"Notified · ETA {eta_minutes(km)} min", RISK["low"]
            app.map.dispatch["done"].add(s["id"])
            app._redraw_map()
            app.page.update()

        place = zone["name"].split(" (")[0]
        app.sim.log_event("extreme", "Emergency",
                          f"Alert from [b]{place}[/b] sent to {len(chosen)} fire stations (ref {ref}).")
        header.value = f"{len(chosen)} fire stations notified"
        body.controls.append(banner(
            f"Reference {ref}. Crews have your location"
            f"{' and call-back number ' + who_phone if who_phone else ''}. "
            "Move away from the fire, keep your phone on, and follow instructions from emergency services.",
            RISK["low"], ft.Icons.CHECK_CIRCLE))
        actions.controls = [
            ft.TextButton("Clear map", on_click=lambda e: (app.clear_dispatch(), app.page.pop_dialog())),
            primary_button("Done", lambda e: app.page.pop_dialog(), color=INFO_BLUE),
        ]
        app.page.update()

    build_form()
    dlg = ft.AlertDialog(
        modal=True, shape=ft.RoundedRectangleBorder(radius=14),
        title=ft.Row([ft.Icon(ft.Icons.SOS, color=EMERGENCY, size=26),
                      txt("Emergency alert", 19, EMERGENCY_DARK, bold=True)], spacing=8),
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
    error = _error_text()

    def close(e=None):
        app.map.pending_pin = None
        app._redraw_map()
        app.page.pop_dialog()

    async def send():
        send_button.disabled = True
        app.page.update()
        row, err = await asyncio.to_thread(reports.add_report, user, lat, lon, kind.value, note.value)
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
         kind, note, error,
         txt("Reports are public and unverified, and show your first name. This does not alert "
             "fire crews. In an emergency use the SOS button or call 112.", 11, FAINT)],
        [ft.TextButton("Cancel", on_click=close), send_button],
        icon=ft.Icons.ADD_LOCATION_ALT,
    )
    app.page.show_dialog(dlg)
