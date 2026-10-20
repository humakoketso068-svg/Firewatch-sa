"""
Settings for the live features. Everything comes from environment variables, so no
secret ever lives in the code. On Render, set them under Environment.

Every feature is optional: with no variables set the app runs as the plain simulation.
"""

import os
import sys

# True when the app runs inside the browser (flet build web / Netlify). The live
# features need a real server, so they switch themselves off there.
IN_BROWSER = sys.platform == "emscripten"


def env(name, default=""):
    return (os.environ.get(name) or default).strip()


def env_int(name, default, lo, hi):
    try:
        value = int(env(name, str(default)))
    except ValueError:
        value = default
    return max(lo, min(hi, value))


def env_float(name, default):
    try:
        return float(env(name, str(default)))
    except ValueError:
        return default


# --- NASA FIRMS (free key: https://firms.modaps.eosdis.nasa.gov/api/map_key/) ---
FIRMS_KEY = env("FIRMS_MAP_KEY")
FIRMS_SOURCE = env("FIRMS_SOURCE", "VIIRS_SNPP_NRT")
FIRMS_DAYS = env_int("FIRMS_DAYS", 2, 1, 5)
REFRESH_MIN = env_int("FIRMS_REFRESH_MIN", 15, 10, 180)   # NASA asks you not to poll faster

# --- Supabase (shared database for reports and alert subscribers) ---
SUPABASE_URL = env("SUPABASE_URL")
SUPABASE_KEY = env("SUPABASE_SERVICE_KEY")                # server-side only, never in the page

# --- SMS through Twilio ---
TWILIO_SID = env("TWILIO_ACCOUNT_SID")
TWILIO_TOKEN = env("TWILIO_AUTH_TOKEN")
TWILIO_FROM = env("TWILIO_FROM")                          # your Twilio number, e.g. +1555...

# --- SMS through a South African provider (set ONE of these; Twilio is the fallback) ---
SMS_PROVIDER = env("SMS_PROVIDER").lower()                 # "bulksms", "clickatell" or "twilio" (auto if empty)
BULKSMS_ID = env("BULKSMS_TOKEN_ID")                       # BulkSMS API token id + secret
BULKSMS_SECRET = env("BULKSMS_TOKEN_SECRET")
CLICKATELL_KEY = env("CLICKATELL_API_KEY")                 # Clickatell One API key

# --- Station console (fire stations log in with this key to see and acknowledge SOS calls) ---
# One shared key:  STATION_KEY=abc123          Several stations:  STATION_KEYS=Komatipoort:abc,Nelspruit:def
STATION_KEY = env("STATION_KEY")
STATION_KEYS = env("STATION_KEYS")

# --- Email through any SMTP server (Gmail needs an "app password") ---
SMTP_HOST = env("SMTP_HOST")
SMTP_PORT = env_int("SMTP_PORT", 587, 1, 65535)
SMTP_USER = env("SMTP_USER")
SMTP_PASS = env("SMTP_PASS")
SMTP_FROM = env("SMTP_FROM") or SMTP_USER

# --- Alerts ---
ALERT_RADIUS_KM = env_float("ALERT_RADIUS_KM", 30.0)      # hotspot this close to a user's town
ALERT_MAX_AGE_H = env_float("ALERT_MAX_AGE_H", 6.0)       # ignore detections older than this
ALERT_COOLDOWN_H = env_float("ALERT_COOLDOWN_H", 3.0)     # at most one message per person per this


def sms_provider():
    """Which SMS service is configured, or '' for none."""
    wanted = {"bulksms": bool(BULKSMS_ID and BULKSMS_SECRET), "clickatell": bool(CLICKATELL_KEY),
              "twilio": bool(TWILIO_SID and TWILIO_TOKEN and TWILIO_FROM)}
    if SMS_PROVIDER in wanted:
        return SMS_PROVIDER if wanted[SMS_PROVIDER] else ""
    for name in ("bulksms", "clickatell", "twilio"):
        if wanted[name]:
            return name
    return ""


def sms_ready():
    return bool(sms_provider())


def station_logins():
    """{key: station label} from STATION_KEY / STATION_KEYS."""
    out = {}
    if STATION_KEY:
        out[STATION_KEY] = "Fire station"
    for part in STATION_KEYS.split(","):
        if ":" in part:
            label, key = part.split(":", 1)
            if label.strip() and key.strip():
                out[key.strip()] = label.strip()
    return out


def email_ready():
    return bool(SMTP_HOST and SMTP_FROM)
