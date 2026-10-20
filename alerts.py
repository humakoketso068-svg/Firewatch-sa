"""
Hometown fire alerts by email and/or SMS.

People opt in from the sign-up or profile dialog. We keep one row per subscriber on
the server (email, number, home town and its coordinates) because accounts themselves
live in each person's own browser and the server could not otherwise reach them.

The background monitor (monitor.py) calls check_and_notify() after every NASA FIRMS
refresh. A person gets a message when a fresh hotspot appears within ALERT_RADIUS_KM
of their town, at most one message per ALERT_COOLDOWN_H hours, and never twice for
the same hotspot.
"""

import hashlib
import json
import smtplib
import threading
import time
from email.message import EmailMessage

import config
import i18n
import places
import sms as sms_service
import store
from stations import distance_km

MODES = ("off", "email", "sms", "both")

_lock = threading.Lock()
_sent = None                 # set of "email|hotspot-id" keys already messaged
_last_msg = {}               # email -> time of the last message


# ---------------------------------------------------------------------------
# Subscribers
# ---------------------------------------------------------------------------

PRIVACY_STEP = 0.05          # degrees (about 5 km): subscriber positions are stored blurred


def blur(value):
    """Round a coordinate to the privacy grid so the server never holds an exact home location."""
    return round(round(value / PRIVACY_STEP) * PRIVACY_STEP, 3)


def who_id(email):
    return hashlib.sha256((email or "").strip().lower().encode()).hexdigest()[:12]


def sync_subscriber(user, zone):
    """Create, update or remove the server-side record for this user."""
    mode = user.get("alerts", "off")
    email = (user.get("email") or "").strip().lower()
    if not email:
        return
    if mode not in MODES or mode == "off":
        store.delete("subscribers", "email", email)
        return
    place = user.get("alert_place")
    if place:                                   # exact town/village chosen by the person
        label = f'{place["name"]}, {place["province"]}' if place.get("province") else place["name"]
        zone_id, zone_name, lat, lon = zone["id"], label, place["lat"], place["lon"]
    else:
        zone_id, zone_name, lat, lon = zone["id"], zone["name"], zone["lat"], zone["lon"]
    store.upsert("subscribers", {
        "email": email, "name": user.get("name", ""), "phone": user.get("phone", ""),
        "zone_id": zone_id, "zone_name": zone_name, "lat": blur(lat), "lon": blur(lon), "alerts": mode,
        "prefs": json.dumps(prefs_of(user)),
    }, key="email")


e164 = sms_service.e164

SEVERITY_ORDER = {"low": 0, "moderate": 1, "high": 2}
MIN_SEV_OPTIONS = [("low", "All detections"), ("moderate", "Moderate and strong"), ("high", "Strong fires only")]


def prefs_of(user):
    """The alert settings stored with a subscriber."""
    return {
        "lang": i18n.lang_ok(user.get("lang", "en")),
        "min_sev": user.get("min_sev") if user.get("min_sev") in SEVERITY_ORDER else "low",
        "quiet": user.get("quiet") if isinstance(user.get("quiet"), list) and len(user.get("quiet")) == 2 else None,
        "radius": max(5, min(100, int(user.get("radius_km") or config.ALERT_RADIUS_KM))),
    }


def severity(hotspot):
    """Strength of a satellite detection from its fire radiative power (MW)."""
    frp = hotspot.get("frp", 0)
    return "high" if frp >= 50 else "moderate" if frp >= 15 else "low"


def local_hour(now=None):
    """Hour of day in South Africa (UTC+2, no daylight saving)."""
    return int(((now or time.time()) + 7200) // 3600) % 24


def in_quiet_hours(quiet, now=None):
    if not quiet:
        return False
    start, end, hour = int(quiet[0]) % 24, int(quiet[1]) % 24, local_hour(now)
    if start == end:
        return False
    return start <= hour < end if start < end else (hour >= start or hour < end)


# ---------------------------------------------------------------------------
# Senders
# ---------------------------------------------------------------------------

def send_sms(phone, body):
    return sms_service.send(phone, body)


def send_email(address, subject, body):
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = config.SMTP_FROM, address, subject
    msg.set_content(body)
    if config.SMTP_PORT == 465:
        server = smtplib.SMTP_SSL(config.SMTP_HOST, config.SMTP_PORT, timeout=20)
    else:
        server = smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=20)
    try:
        if config.SMTP_PORT != 465:
            server.starttls()
        if config.SMTP_USER:
            server.login(config.SMTP_USER, config.SMTP_PASS)
        server.send_message(msg)
    finally:
        try:
            server.quit()
        except Exception:
            pass


def build_message(zone_name, count, km, where="", lang="en"):
    place = f"{zone_name} ({where})" if where else zone_name
    sms = i18n.t(lang, "alert_sms", n=count, km=f"{km:.0f}", place=place)
    mail = (sms + "\n\n"
            "Keep your phone on and follow instructions from local authorities.\n"
            "In an emergency call 112.\n\n"
            "You get this because you turned on fire alerts in Firewatch. "
            "You can switch them off any time in your profile.")
    return sms, mail


def _deliver(mode, phone, email, sms_text, mail_text, subject="Firewatch fire alert"):
    """Try each chosen channel. Returns (channels_used, errors)."""
    used, errors = [], []
    if mode in ("sms", "both"):
        if config.sms_ready():
            try:
                send_sms(phone, sms_text)
                used.append("SMS")
            except Exception as err:
                errors.append(f"SMS failed: {err}")
        else:
            errors.append("SMS is not set up on the server")
    if mode in ("email", "both"):
        if config.email_ready():
            try:
                send_email(email, subject, mail_text)
                used.append("email")
            except Exception as err:
                errors.append(f"email failed: {err}")
        else:
            errors.append("email is not set up on the server")
    return used, errors


def send_test(user):
    """Used by the 'Send a test alert' button. Returns a message for the person."""
    mode = user.get("alerts", "off")
    if mode == "off":
        return "Choose Email, SMS or both, press Save, then send the test."
    sms, mail = build_message((user.get("alert_place") or {}).get("name") or user.get("home_zone_name", "your town"), 1, 12,
                            lang=user.get("lang", "en"))
    used, errors = _deliver(mode, user.get("phone", ""), user.get("email", ""),
                            "TEST " + sms, "THIS IS A TEST.\n\n" + mail, subject="Firewatch test alert")
    if used:
        return "Test sent by " + " and ".join(used) + ". Check your phone or inbox." + (
            " (" + "; ".join(errors) + ")" if errors else "")
    return "Could not send: " + "; ".join(errors)


# ---------------------------------------------------------------------------
# Matching hotspots to subscribers
# ---------------------------------------------------------------------------

def _load_sent():
    global _sent
    if _sent is None:
        _sent = set()
        try:
            since = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 3 * 86400))
            for row in store.select("alert_log", since=since, limit=5000):
                _sent.add(row.get("key"))
        except store.StoreError:
            pass
    return _sent


def check_and_notify(hotspots, now=None, deliver=None, report=None):
    """Message subscribers who have a fresh hotspot near their town, respecting their
    settings (radius, minimum strength, quiet hours, language).
    Returns the number of people messaged. `deliver` is replaceable for tests; `report`,
    if a list, receives (lat, lon, channels) for each person messaged (for the timeline)."""
    now = now or time.time()
    deliver = deliver or _deliver
    if not hotspots or not (config.sms_ready() or config.email_ready()):
        return 0
    try:
        subscribers = store.select("subscribers", limit=5000)
    except store.StoreError as err:
        print("alerts: could not read subscribers:", err)
        return 0

    with _lock:
        sent = _load_sent()
        messaged = 0
        for sub in subscribers:
            email, mode = sub.get("email"), sub.get("alerts", "off")
            if not email or mode not in ("email", "sms", "both"):
                continue
            if now - _last_msg.get(email, 0) < config.ALERT_COOLDOWN_H * 3600:
                continue
            try:
                prefs = json.loads(sub.get("prefs") or "{}")
            except (TypeError, ValueError):
                prefs = {}
            radius = float(prefs.get("radius") or config.ALERT_RADIUS_KM)
            wanted = SEVERITY_ORDER.get(prefs.get("min_sev"), 0)
            quiet = in_quiet_hours(prefs.get("quiet"), now)
            near = []
            for h in hotspots:
                if now - h["ts"] > config.ALERT_MAX_AGE_H * 3600:
                    continue
                sev = SEVERITY_ORDER[severity(h)]
                if sev < wanted or (quiet and sev < SEVERITY_ORDER["high"]):
                    continue                       # below their threshold, or quiet hours
                km = distance_km(sub["lat"], sub["lon"], h["lat"], h["lon"])
                if km <= radius and f"{email}|{h['id']}" not in sent:
                    near.append((km, h))
            if not near:
                continue
            near.sort(key=lambda item: item[0])
            sms, mail = build_message(sub.get("zone_name", "your town"), len(near), near[0][0],
                                      places.where(near[0][1]["lat"], near[0][1]["lon"]),
                                      lang=prefs.get("lang", "en"))
            used, errors = deliver(mode, sub.get("phone", ""), email, sms, mail)
            for err in errors:
                print(f"alerts: {email}: {err}")
            if not used:
                continue
            _last_msg[email] = now
            messaged += 1
            _log_message(email, "alert", used, sub.get("zone_name", ""), near[0][0])
            if isinstance(report, list):
                report.append((near[0][1]["lat"], near[0][1]["lon"], used))
            for _, h in near[:50]:
                key = f"{email}|{h['id']}"
                sent.add(key)
                try:
                    store.insert("alert_log", {"key": key})
                except store.StoreError:
                    pass
        return messaged


# ---------------------------------------------------------------------------
# Message log and station/FPA broadcasts
# ---------------------------------------------------------------------------

def _log_message(email, kind, channels, place, km=None):
    """One row per message sent. Holds a hashed id, never the email or phone number."""
    try:
        store.insert("message_log", {"who": who_id(email), "kind": kind, "channels": "+".join(channels),
                                     "place": place[:80], "km": None if km is None else round(km)})
    except store.StoreError:
        pass


def history_for(email, limit=10):
    """The last messages Firewatch sent to this person (newest first)."""
    try:
        rows = store.select("message_log", limit=1000)
    except store.StoreError:
        return []
    me = who_id(email)
    return [r for r in rows if r.get("who") == me][:limit]


def broadcast(lat, lon, radius_km, text, subject="Firewatch notice", now=None, deliver=None):
    """Message every subscriber whose home is within radius_km of a point (used by FPA notices).
    Ignores quiet hours and cooldown: an evacuation warning must get through.
    Returns (people_messaged, list_of_error_strings)."""
    deliver = deliver or _deliver
    if not (config.sms_ready() or config.email_ready()):
        return 0, ["No SMS provider or email server is set up on the server."]
    try:
        subscribers = store.select("subscribers", limit=5000)
    except store.StoreError as err:
        return 0, [f"Could not read subscribers: {err}"]
    sent, errors = 0, []
    for sub in subscribers:
        email, mode = sub.get("email"), sub.get("alerts", "off")
        if not email or mode not in ("email", "sms", "both"):
            continue
        try:
            if distance_km(float(sub["lat"]), float(sub["lon"]), lat, lon) > radius_km:
                continue
        except (KeyError, TypeError, ValueError):
            continue
        used, errs = deliver(mode, sub.get("phone", ""), email, text, text + "\n\nIn an emergency call 112.", subject)
        errors += [f"{email.split('@')[0][:2]}***: {e}" for e in errs]
        if used:
            sent += 1
            _log_message(email, "notice", used, sub.get("zone_name", ""))
    return sent, errors[:5]
