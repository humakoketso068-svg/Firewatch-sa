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
from stations import distance_km

KINDS = {"smoke": "Smoke seen", "flames": "Flames seen", "house": "House or building fire",
         "informal": "Informal settlement fire", "hazard": "Other fire hazard"}
MAX_ADDRESS = 80
SATELLITE_KM = 5.0          # a satellite hotspot this close (within 12 h) backs a report up
VOTES_TO_CONFIRM = 2        # or this many other people confirming it
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


def add_report(user, lat, lon, kind, note, address=""):
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
    address = " ".join((address or "").split())[:MAX_ADDRESS]
    if address:                                  # kept inside the note so no extra column is needed
        note = (f"Address: {address}. " + note)[:MAX_NOTE + MAX_ADDRESS + 12]

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


def vote(report_id, user):
    """Someone else confirms a report ("I can see this too"). Returns (votes, error)."""
    if not user:
        return None, "Log in to confirm a report."
    voter = reporter_id(user["email"])
    try:
        since = _iso(datetime.now(timezone.utc) - timedelta(hours=SHOW_HOURS))
        report = next((r for r in store.select("reports", since=since, limit=300) if r.get("id") == report_id), None)
        if report is None:
            return None, "That report has expired."
        if report.get("reporter_id") == voter:
            return None, "You cannot confirm your own report."
        votes = [v for v in store.select("report_votes", since=since, limit=2000) if v.get("report_id") == report_id]
        if any(v.get("voter_id") == voter for v in votes):
            return len(votes), "You already confirmed this report."
        store.insert("report_votes", {"report_id": report_id, "voter_id": voter})
    except store.StoreError as err:
        return None, f"Could not save your confirmation ({err})."
    with _cache_lock:
        _cache["at"] = 0.0
    return len(votes) + 1, None


def verification(report, votes, hotspots, now=None):
    """'satellite' (a NASA hotspot nearby), 'confirmed' (enough people), or 'unverified'."""
    now = now or time.time()
    for h in hotspots or ():
        if abs(h["ts"] - report["ts"]) <= 12 * 3600 and distance_km(report["lat"], report["lon"], h["lat"], h["lon"]) <= SATELLITE_KM:
            return "satellite"
    return "confirmed" if votes >= VOTES_TO_CONFIRM else "unverified"


VERIFY_LABEL = {"satellite": "Matches a NASA satellite hotspot", "confirmed": "Confirmed by other people",
                "unverified": "Not yet verified"}


def recent_reports(force=False, hotspots=None):
    """Reports from the last 24 h, newest first, each with votes and a verification level.
    Cached for a few seconds; the satellite match is recalculated every call."""
    with _cache_lock:
        if not force and time.time() - _cache["at"] < CACHE_SECONDS:
            return _with_verification(_cache["rows"], hotspots)
    try:
        since = _iso(datetime.now(timezone.utc) - timedelta(hours=SHOW_HOURS))
        raw = store.select("reports", since=since, limit=300)
        vote_rows = store.select("report_votes", since=since, limit=3000)
    except store.StoreError:
        with _cache_lock:                        # keep showing what we had
            return _with_verification(_cache["rows"], hotspots)
    tally = {}
    for v in vote_rows:
        tally[v.get("report_id")] = tally.get(v.get("report_id"), 0) + 1
    rows = []
    for r in raw:
        ts = _to_epoch(r.get("created_at"))
        if ts is None or r.get("kind") not in KINDS:
            continue
        try:
            rows.append({
                "id": r.get("id"), "lat": float(r["lat"]), "lon": float(r["lon"]),
                "kind": r["kind"], "kind_label": KINDS[r["kind"]],
                "note": str(r.get("note") or "")[:MAX_NOTE + MAX_ADDRESS + 12],
                "reporter": str(r.get("reporter") or "")[:30], "ts": ts,
                "votes": tally.get(r.get("id"), 0), "rid": r.get("reporter_id", ""),
            })
        except (KeyError, TypeError, ValueError):
            continue
    with _cache_lock:
        _cache["at"] = time.time()
        _cache["rows"] = rows
    return _with_verification(rows, hotspots)


def _with_verification(rows, hotspots):
    out = []
    for r in rows:
        r = dict(r)
        r["verified"] = verification(r, r.get("votes", 0), hotspots)
        out.append(r)
    return out
