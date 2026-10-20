"""
SOS: what really happens when someone presses the emergency button.

1. An incident record is saved. Fire stations that use the Station console (see
   dialogs.show_console) see it at once and can acknowledge and dispatch it.
2. Stations in stations.json that are marked "verified" and have an SMS number or email
   are messaged directly.
3. The person's emergency contacts get an SMS in the person's language.

Every step records an honest outcome. "Sent" means the SMS provider or mail server
accepted the message; it does not mean a person has read it. When no station in the
directory can be reached directly, the result says so and tells the person to call 112.
"""

import time

import alerts
import config
import i18n
import incidents
from stations import FIRE_STATIONS, USING_REAL_DIRECTORY, contactable, distance_km, eta_minutes

ETYPES = {
    "veld": "Veld / grass fire",
    "house_kitchen": "House fire: kitchen",
    "house_electrical": "House fire: electrical",
    "informal": "Informal settlement fire",
    "other": "Other fire",
}
MAX_DIRECT = 3            # nearest reachable stations that get a direct message


def maps_link(lat, lon):
    return f"https://maps.google.com/?q={lat:.5f},{lon:.5f}"


def station_text(inc, who, phone):
    d = inc["data"]
    parts = [f"FIREWATCH SOS {inc['id'][-6:].upper()}: {ETYPES.get(d.get('etype'), 'Fire')} near {inc['place']}."]
    if d.get("address"):
        parts.append(f"Address: {d['address'][:80]}.")
    parts.append(f"GPS {inc['lat']:.5f},{inc['lon']:.5f} {maps_link(inc['lat'], inc['lon'])}")
    parts.append(f"Caller: {who or 'unknown'} {phone or ''}".strip() + ".")
    if d.get("note"):
        parts.append(d["note"][:80])
    return " ".join(parts)


def reachable_stations(lat, lon):
    ranked = sorted(((s, distance_km(lat, lon, s["lat"], s["lon"])) for s in FIRE_STATIONS), key=lambda i: i[1])
    return [(s, km) for s, km in ranked if contactable(s)][:MAX_DIRECT]


def trigger(lat, lon, place, who, phone, etype="veld", address="", note="", lang="en",
            contacts=(), email=""):
    """Run the whole SOS. Blocking (network calls): call from a thread.
    Returns the saved incident; its data["deliveries"] lists what happened to each message."""
    inc = incidents.create("sos", status="new", title=f"SOS: {ETYPES.get(etype, 'Fire')}", place=place,
                           lat=round(lat, 5), lon=round(lon, 5))
    inc["data"] = {"etype": etype, "address": address, "note": note, "caller": who, "phone": phone,
                   "email": email, "lang": lang, "deliveries": []}
    incidents.event(inc, f"SOS received from {who or 'a caller'} near {place}")
    incidents.save(inc)

    text = station_text(inc, who, phone)
    targets = reachable_stations(lat, lon)
    deliveries = inc["data"]["deliveries"]
    for s, km in targets:
        used, errors = [], []
        if s.get("sms") and config.sms_ready():
            try:
                alerts.send_sms(s["sms"], text)
                used.append("SMS")
            except Exception as err:
                errors.append(f"SMS failed: {err}")
        if s.get("email") and config.email_ready():
            try:
                alerts.send_email(s["email"], f"SOS {inc['id'][-6:].upper()} near {place}", text)
                used.append("email")
            except Exception as err:
                errors.append(f"email failed: {err}")
        if not used and not errors:
            errors.append("no SMS provider or email server is set up")
        deliveries.append({"to": s["name"], "km": round(km), "eta": eta_minutes(km), "ok": bool(used),
                           "via": " + ".join(used), "error": "; ".join(errors), "at": time.time()})
        incidents.event(inc, f"Sent to {s['name']} by {' + '.join(used)}" if used
                        else f"Could not reach {s['name']}: {'; '.join(errors)}")

    if not targets:
        why = ("no station in the directory has a confirmed SMS number or email yet"
               if USING_REAL_DIRECTORY else "the station directory is only an illustrative sample")
        incidents.event(inc, f"No fire station could be messaged directly ({why}). Caller told to call 112.")

    for c in list(contacts)[:3]:
        body = i18n.t(lang, "contact_sms", name=who or "Someone", place=place, phone=phone or "")
        try:
            if not config.sms_ready():
                raise RuntimeError("no SMS provider is set up")
            alerts.send_sms(c["phone"], body)
            deliveries.append({"to": f"Contact: {c['name']}", "ok": True, "via": "SMS", "error": "", "at": time.time()})
            incidents.event(inc, f"SMS sent to emergency contact {c['name']}")
        except Exception as err:
            deliveries.append({"to": f"Contact: {c['name']}", "ok": False, "via": "", "error": str(err), "at": time.time()})
            incidents.event(inc, f"Could not message emergency contact {c['name']}: {err}")

    incidents.event(inc, "Waiting for a fire station to acknowledge in the Station console")
    incidents.save(inc)
    return inc
