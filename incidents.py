"""
Incident log: every SOS call and every satellite-detected fire gets a record with a
timeline (detected, alerts sent, acknowledged, dispatched...).

Stored through store.py (Supabase table "incidents", or a local JSON file). Timelines are
kept as a JSON list in the "events" column.
"""

import json
import secrets
import threading
import time
from datetime import datetime, timezone

import places
import store
from stations import distance_km

FIRE_STATUS = {"active": "Active", "quiet": "No new detections", "contained": "Contained",
               "extinguished": "Extinguished", "closed": "Closed (no detections)",
               "evacuation": "Evacuation warning", "rescue_needed": "Rescue needed",
               "extrication": "Extrication equipment needed", "cleared": "Cleared"}
# What a Fire Protection Association (FPA) or station can post from the console
FPA_STATUS = {"active": "Active fire", "evacuation": "Evacuation warning", "contained": "Contained",
              "extinguished": "Extinguished"}
RESCUE_STATUS = {"rescue_needed": "Road or rescue incident", "extrication": "Extrication equipment needed (Jaws of Life)",
                 "cleared": "Cleared"}
CLOSED = ("extinguished", "cleared", "closed")
SOS_STATUS = {"new": "New", "acknowledged": "Acknowledged", "dispatched": "Crew dispatched",
              "resolved": "Resolved"}
QUIET_AFTER_H = 12
CLOSE_AFTER_H = 36

_lock = threading.Lock()


def _iso(ts=None):
    return datetime.fromtimestamp(ts or time.time(), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_json(text, default):
    try:
        value = json.loads(text) if isinstance(text, str) else text
        return value if isinstance(value, type(default)) else default
    except (TypeError, ValueError):
        return default


def parse(row):
    """Row from the store -> dict with events (list) and data (dict) decoded."""
    row = dict(row)
    row["events"] = _load_json(row.get("events"), [])
    row["data"] = _load_json(row.get("data"), {})
    return row


def _pack(inc):
    row = {k: v for k, v in inc.items() if k not in ("events", "data")}
    row["events"] = json.dumps(inc.get("events", []))
    row["data"] = json.dumps(inc.get("data", {}))
    row["updated_at"] = _iso()
    return row


def save(inc):
    inc.setdefault("created_at", _iso())
    store.upsert("incidents", _pack(inc), key="id")
    return inc


def event(inc, text, ts=None):
    inc["events"].append({"ts": ts or time.time(), "text": text})
    inc["events"].sort(key=lambda e: e["ts"])


def create(kind, **fields):
    inc = {"id": fields.pop("id", f"{kind}-{int(time.time())}-{secrets.token_hex(3)}"),
           "kind": kind, "status": fields.pop("status", "new"), "events": [], "data": {},
           "created_at": _iso()}
    inc.update(fields)
    return inc


def get(incident_id):
    for row in store.select("incidents", limit=500):
        if row.get("id") == incident_id:
            return parse(row)
    return None


def recent(kind=None, limit=60, since_hours=None):
    since = _iso(time.time() - since_hours * 3600) if since_hours else None
    rows = [parse(r) for r in store.select("incidents", since=since, limit=500)]
    if kind:
        rows = [r for r in rows if r.get("kind") == kind]
    rows.sort(key=lambda r: r.get("updated_at") or r.get("created_at") or "", reverse=True)
    return rows[:limit]


def set_status(incident_id, status, by, text=None):
    """Used by the station console. Returns the updated incident or None."""
    with _lock:
        inc = get(incident_id)
        if not inc:
            return None
        inc["status"] = status
        label = (SOS_STATUS if inc["kind"] == "sos" else FIRE_STATUS).get(status, status)
        event(inc, text or f"{label} by {by}")
        if status == "acknowledged":
            inc["data"].update(ack_by=by, ack_at=time.time())
        elif status == "dispatched":
            inc["data"].update(dispatch_by=by, dispatch_at=time.time())
        save(inc)
        return inc


# ---------------------------------------------------------------------------
# Satellite fires -> incidents
# ---------------------------------------------------------------------------

def sync_fires(clusters, hotspots, now=None):
    """Create/update one incident per town with fresh hotspots. Call after each FIRMS refresh."""
    now = now or time.time()
    ts_of = {h["id"]: h["ts"] for h in hotspots}
    with _lock:
        try:
            open_by_zone = {}
            for inc in recent("fire", limit=300):
                if inc.get("status") in ("active", "quiet"):
                    open_by_zone[inc["data"].get("zone_id")] = inc
        except store.StoreError as err:
            print("incidents:", err)
            return
        seen = set()
        for c in clusters:
            zone = c["zone_id"]
            seen.add(zone)
            last = max((ts_of.get(i, 0) for i in c["ids"]), default=now)
            first = min((ts_of.get(i, now) for i in c["ids"]), default=now)
            where = places.where(c["lat"], c["lon"]) or f'{c["zone_name"].split(" (")[0]}, {c["province"]}'
            inc = open_by_zone.get(zone)
            try:
                if inc is None:
                    inc = create("fire", id=f"fire-{zone}-{time.strftime('%Y%m%d%H%M', time.gmtime(first))}",
                                 status="active", title=f"Fire near {where}", place=where,
                                 lat=round(c["lat"], 4), lon=round(c["lon"], 4))
                    inc["data"] = {"zone_id": zone, "count": c["count"], "peak": c["count"],
                                   "frp": round(c["frp_sum"]), "last_ts": last}
                    event(inc, f'First satellite detection (NASA VIIRS): {c["count"]} hotspot(s) near {where}', first)
                    event(inc, "Incident opened in Firewatch", now)
                else:
                    d = inc["data"]
                    if inc["status"] == "quiet":
                        inc["status"] = "active"
                        event(inc, "New detections: the fire is active again", now)
                    if c["count"] >= max(2, d.get("peak", 1) * 2):
                        event(inc, f'Growing: {c["count"]} hotspots now (was {d.get("peak", 1)})', now)
                    d.update(count=c["count"], peak=max(d.get("peak", 0), c["count"]),
                             frp=round(c["frp_sum"]), last_ts=max(last, d.get("last_ts", 0)))
                    inc["lat"], inc["lon"] = round(c["lat"], 4), round(c["lon"], 4)
                save(inc)
            except store.StoreError as err:
                print("incidents:", err)
        for zone, inc in open_by_zone.items():
            if zone in seen:
                continue
            quiet_h = (now - inc["data"].get("last_ts", now)) / 3600
            try:
                if inc["status"] == "active" and quiet_h >= QUIET_AFTER_H:
                    inc["status"] = "quiet"
                    event(inc, f"No new detections for {QUIET_AFTER_H} hours", now)
                    save(inc)
                elif inc["status"] == "quiet" and quiet_h >= CLOSE_AFTER_H:
                    inc["status"] = "closed"
                    event(inc, f"Closed: no detections for {CLOSE_AFTER_H} hours (satellite data cannot confirm the fire is out)", now)
                    save(inc)
            except store.StoreError as err:
                print("incidents:", err)


def note_alerts(sent, now=None):
    """sent: list of (lat, lon, channels) for each person messaged. Adds ONE timeline entry
    per fire incident, so the timeline shows when alerts went out without listing people."""
    now = now or time.time()
    if not sent:
        return
    with _lock:
        try:
            fires = [i for i in recent("fire", limit=300) if i.get("status") in ("active", "quiet")]
        except store.StoreError:
            return
        groups = {}
        for lat, lon, channels in sent:
            best, best_km = None, 80.0
            for inc in fires:
                try:
                    km = distance_km(lat, lon, float(inc["lat"]), float(inc["lon"]))
                except (KeyError, TypeError, ValueError):
                    continue
                if km < best_km:
                    best, best_km = inc, km
            if best:
                groups.setdefault(best["id"], (best, []))[1].append(channels)
        for inc, lists in groups.values():
            sms = sum(1 for ch in lists if "SMS" in ch)
            mail = sum(1 for ch in lists if "email" in ch)
            event(inc, f"Alerts sent to {len(lists)} subscriber(s) nearby (SMS {sms}, email {mail})", now)
            inc["data"]["alerts"] = inc["data"].get("alerts", 0) + len(lists)
            try:
                save(inc)
            except store.StoreError:
                pass


def clock(ts):
    return time.strftime("%d %b %H:%M", time.gmtime(ts + 7200)) + " SAST"


# ---------------------------------------------------------------------------
# Notices posted by stations and Fire Protection Associations
# ---------------------------------------------------------------------------

def post_notice(kind, status, place, lat, lon, text, by, radius_km=0):
    """kind 'fpa' (fire status) or 'rescue' (road / extrication). Saved as an incident so it
    shows on the map and in the incident list. Returns the incident."""
    labels = FPA_STATUS if kind == "fpa" else RESCUE_STATUS
    title = f"{labels.get(status, status)}: {place}"
    inc = create(kind, status=status, title=title, place=place, lat=round(lat, 4), lon=round(lon, 4))
    inc["data"] = {"text": text[:300], "by": by, "radius_km": radius_km}
    event(inc, f"{labels.get(status, status)} posted by {by}")
    save(inc)
    return inc


def active_notices(hours=48):
    """Open FPA / rescue notices for the map layer."""
    try:
        rows = recent(None, limit=200, since_hours=hours)
    except store.StoreError:
        return []
    return [r for r in rows if r.get("kind") in ("fpa", "rescue") and r.get("status") not in CLOSED]
