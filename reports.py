"""
Citizen reports: a signed-in user drops a pin for "I can see smoke here".

Reports show on the map for 24 hours. To limit abuse: login required, five reports
per person per hour, short notes, and only places inside South Africa's bounding box.
Notes are shown as plain text, never as markup.
"""

import hashlib
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone

import store

KINDS = {"smoke": "Smoke seen", "flames": "Flames seen", "hazard": "Other fire hazard"}
MAX_NOTE = 200
MAX_PER_HOUR = 5
SHOW_HOURS = 24
CACHE_SECONDS = 30
BOUNDS = (-35.2, 16.3, -21.9, 33.1)         # south, west, north, east

_cache = {"at": 0.0, "rows": []}
_cache_lock = threading.Lock()


def _iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def reporter_id(email):
    return hashlib.sha256((email or "").strip().lower().encode()).hexdigest()[:12]


def add_report(user, lat, lon, kind, note):
    """Returns (row, error). Exactly one is None."""
    if not user:
        return None, "Log in to send a report."
    if kind not in KINDS:
        return None, "Choose what you can see."
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        return None, "Pick a spot on the map."
    s, w, n, e = BOUNDS
    if not (s <= lat <= n and w <= lon <= e):
        return None, "That spot is outside South Africa."
    note = " ".join((note or "").split())[:MAX_NOTE]

    rid = reporter_id(user["email"])
    try:
        since = _iso(datetime.now(timezone.utc) - timedelta(hours=1))
        recent = store.select("reports", since=since, limit=500)
    except store.StoreError as err:
        return None, f"Could not reach the report database ({err})."
    if sum(1 for r in recent if r.get("reporter_id") == rid) >= MAX_PER_HOUR:
        return None, "You have sent several reports in the last hour. Please wait a while."

    row = {
        "id": secrets.token_hex(6), "lat": round(lat, 5), "lon": round(lon, 5),
        "kind": kind, "note": note,
        "reporter": (user.get("name") or "A user").split()[0][:30], "reporter_id": rid,
    }
    try:
        store.insert("reports", row)
    except store.StoreError as err:
        return None, f"Could not save your report ({err})."
    with _cache_lock:
        _cache["at"] = 0.0                       # next read picks the new report up
    return row, None


def _to_epoch(value):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def recent_reports(force=False):
    """Reports from the last 24 h, newest first, cached for a few seconds."""
    with _cache_lock:
        if not force and time.time() - _cache["at"] < CACHE_SECONDS:
            return list(_cache["rows"])
    try:
        since = _iso(datetime.now(timezone.utc) - timedelta(hours=SHOW_HOURS))
        raw = store.select("reports", since=since, limit=300)
    except store.StoreError:
        with _cache_lock:                        # keep showing what we had
            return list(_cache["rows"])
    rows = []
    for r in raw:
        ts = _to_epoch(r.get("created_at"))
        if ts is None or r.get("kind") not in KINDS:
            continue
        try:
            rows.append({
                "id": r.get("id"), "lat": float(r["lat"]), "lon": float(r["lon"]),
                "kind": r["kind"], "kind_label": KINDS[r["kind"]],
                "note": str(r.get("note") or "")[:MAX_NOTE],
                "reporter": str(r.get("reporter") or "")[:30], "ts": ts,
            })
        except (KeyError, TypeError, ValueError):
            continue
    with _cache_lock:
        _cache["at"] = time.time()
        _cache["rows"] = rows
    return list(rows)
