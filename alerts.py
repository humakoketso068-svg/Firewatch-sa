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

import base64
import smtplib
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from email.message import EmailMessage

import config
import store
from stations import distance_km

MODES = ("off", "email", "sms", "both")

_lock = threading.Lock()
_sent = None                 # set of "email|hotspot-id" keys already messaged
_last_msg = {}               # email -> time of the last message


# ---------------------------------------------------------------------------
# Subscribers
# ---------------------------------------------------------------------------

def sync_subscriber(user, zone):
    """Create, update or remove the server-side record for this user."""
    mode = user.get("alerts", "off")
    email = (user.get("email") or "").strip().lower()
    if not email:
        return
    if mode not in MODES or mode == "off":
        store.delete("subscribers", "email", email)
        return
    store.upsert("subscribers", {
        "email": email, "name": user.get("name", ""), "phone": user.get("phone", ""),
        "zone_id": zone["id"], "zone_name": zone["name"],
        "lat": zone["lat"], "lon": zone["lon"], "alerts": mode,
    }, key="email")


def e164(phone):
    """South African numbers: 082 123 4567 -> +27821234567."""
    p = "".join(ch for ch in (phone or "") if ch.isdigit() or ch == "+")
    if p.startswith("+"):
        return p
    if p.startswith("0") and len(p) == 10:
        return "+27" + p[1:]
    if p.startswith("27") and len(p) == 11:
        return "+" + p
    return p


# ---------------------------------------------------------------------------
# Senders
# ---------------------------------------------------------------------------

def send_sms(phone, body):
    url = f"https://api.twilio.com/2010-04-01/Accounts/{config.TWILIO_SID}/Messages.json"
    data = urllib.parse.urlencode({"To": e164(phone), "From": config.TWILIO_FROM, "Body": body}).encode()
    token = base64.b64encode(f"{config.TWILIO_SID}:{config.TWILIO_TOKEN}".encode()).decode()
    req = urllib.request.Request(url, data=data, method="POST", headers={"Authorization": "Basic " + token})
    try:
        with urllib.request.urlopen(req, timeout=20):
            return
    except urllib.error.HTTPError as err:
        raise RuntimeError(f"Twilio said {err.code}: {err.read().decode('utf-8', 'replace')[:120]}") from None


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


def build_message(zone_name, count, km):
    plural = "s" if count != 1 else ""
    sms = (f"Firewatch: satellite detected {count} fire hotspot{plural}, about {km:.0f} km from "
           f"{zone_name}. Stay alert and follow local authorities. Emergency: 112.")
    mail = (f"NASA satellites detected {count} fire hotspot{plural} about {km:.0f} km from {zone_name}.\n\n"
            "Stay alert, keep your phone on and follow instructions from local authorities.\n"
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
    sms, mail = build_message(user.get("home_zone_name", "your town"), 1, 12)
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


def check_and_notify(hotspots, now=None, deliver=None):
    """Message subscribers who have a fresh hotspot near their town.
    Returns the number of people messaged. `deliver` is replaceable for tests."""
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
            near = []
            for h in hotspots:
                if now - h["ts"] > config.ALERT_MAX_AGE_H * 3600:
                    continue
                km = distance_km(sub["lat"], sub["lon"], h["lat"], h["lon"])
                if km <= config.ALERT_RADIUS_KM and f"{email}|{h['id']}" not in sent:
                    near.append((km, h))
            if not near:
                continue
            near.sort(key=lambda item: item[0])
            sms, mail = build_message(sub.get("zone_name", "your town"), len(near), near[0][0])
            used, errors = deliver(mode, sub.get("phone", ""), email, sms, mail)
            for err in errors:
                print(f"alerts: {email}: {err}")
            if not used:
                continue
            _last_msg[email] = now
            messaged += 1
            for _, h in near[:50]:
                key = f"{email}|{h['id']}"
                sent.add(key)
                try:
                    store.insert("alert_log", {"key": key})
                except store.StoreError:
                    pass
        return messaged
