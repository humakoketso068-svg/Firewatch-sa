"""
NASA FIRMS: real satellite fire detections ("hotspots") for South Africa.

FIRMS is NASA's Fire Information for Resource Management System. The VIIRS satellite
instruments see fires from space and the data is published within about three hours.
This module downloads the last few days of detections for South Africa and its
borders, keeps them in memory (and in a small file so a restart still has data),
and groups them by the nearest sensor town.

Needs a free key in the FIRMS_MAP_KEY environment variable, and a real server
(Render etc.); a browser-only build cannot call the API without exposing the key.
"""

import csv
import io
import json
import threading
import time
import urllib.request
from datetime import datetime, timezone

import config
import store
from stations import distance_km

BBOX = "16.4,-35.0,33.0,-22.0"      # west, south, east, north
MAX_POINTS = 600                    # strongest detections only, keeps the map light
CLUSTER_RADIUS_KM = 60              # a hotspot counts as "near" a town inside this

CONF_LABEL = {"h": "high", "n": "nominal", "l": "low"}


class FirmsError(Exception):
    pass


_state = {"hotspots": [], "fetched_at": None, "error": None}
_lock = threading.Lock()
_fetch_lock = threading.Lock()


def available():
    return bool(config.FIRMS_KEY) and not config.IN_BROWSER


def snapshot():
    with _lock:
        return dict(_state)


def _safe(message):
    key = config.FIRMS_KEY
    return message.replace(key, "***") if key else message


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def parse(text):
    """FIRMS CSV text -> list of hotspot dicts, strongest first."""
    text = (text or "").strip()
    lines = text.splitlines()
    if not lines or "latitude" not in lines[0].lower():
        # FIRMS answers a bad key or a rate limit with a plain-text message.
        raise FirmsError(text[:120] or "empty response from NASA FIRMS")
    out = []
    for row in csv.DictReader(io.StringIO(text)):
        try:
            lat, lon = float(row["latitude"]), float(row["longitude"])
        except (KeyError, TypeError, ValueError):
            continue
        conf = (row.get("confidence") or "").strip().lower()
        if conf in ("l", "low"):
            continue                                  # skip the least reliable detections
        if conf.isdigit() and int(conf) < 30:
            continue
        try:
            frp = float(row.get("frp") or 0)
        except ValueError:
            frp = 0.0
        date = (row.get("acq_date") or "").strip()
        hhmm = (row.get("acq_time") or "0").strip().zfill(4)
        try:
            ts = datetime.strptime(date + hhmm, "%Y-%m-%d%H%M").replace(tzinfo=timezone.utc).timestamp()
        except ValueError:
            continue
        out.append({
            "id": f"{lat:.4f}_{lon:.4f}_{date}_{hhmm}",
            "lat": lat, "lon": lon, "frp": frp,
            "conf": CONF_LABEL.get(conf, f"{conf}%" if conf.isdigit() else "nominal"),
            "ts": ts,
        })
    out.sort(key=lambda h: -h["frp"])
    return out[:MAX_POINTS]


# ---------------------------------------------------------------------------
# Download + cache
# ---------------------------------------------------------------------------

def _download():
    url = (f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/"
           f"{config.FIRMS_KEY}/{config.FIRMS_SOURCE}/{BBOX}/{config.FIRMS_DAYS}")
    req = urllib.request.Request(url, headers={"User-Agent": "Firewatch/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", "replace")


def _cache_file():
    return store.data_dir() / "firms_cache.json"


def _save_disk(hotspots, fetched_at):
    try:
        path = _cache_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"fetched_at": fetched_at, "hotspots": hotspots}), encoding="utf-8")
    except OSError:
        pass


def _load_disk():
    try:
        data = json.loads(_cache_file().read_text(encoding="utf-8"))
        with _lock:
            _state["hotspots"] = data["hotspots"]
            _state["fetched_at"] = data["fetched_at"]
    except (OSError, ValueError, KeyError, TypeError):
        pass


def refresh(force=False):
    """Download new data if the cache is older than the refresh interval.
    Never raises: on failure the old data stays and `error` says why."""
    if not available():
        return snapshot()
    with _fetch_lock:
        state = snapshot()
        fresh = state["fetched_at"] and time.time() - state["fetched_at"] < config.REFRESH_MIN * 60 * 0.9
        if fresh and not force:
            return state
        try:
            hotspots = parse(_download())
            now = time.time()
            with _lock:
                _state.update(hotspots=hotspots, fetched_at=now, error=None)
            _save_disk(hotspots, now)
        except Exception as err:                       # keep serving the last good data
            with _lock:
                _state["error"] = _safe(f"{type(err).__name__}: {err}")[:200]
    return snapshot()


if not config.IN_BROWSER:
    _load_disk()


# ---------------------------------------------------------------------------
# Grouping hotspots by the nearest sensor town
# ---------------------------------------------------------------------------

def nearest_zone(lat, lon, zones):
    best, best_km = None, 1e9
    for z in zones:
        km = distance_km(lat, lon, z["lat"], z["lon"])
        if km < best_km:
            best, best_km = z, km
    return best, best_km


def cluster(hotspots, zones, max_km=CLUSTER_RADIUS_KM):
    """Group hotspots by nearest town (within max_km). Biggest fires first."""
    groups = {}
    for h in hotspots:
        zone, km = nearest_zone(h["lat"], h["lon"], zones)
        if zone is None or km > max_km:
            continue
        groups.setdefault(zone["id"], {"zone": zone, "hs": []})["hs"].append(h)
    out = []
    for g in groups.values():
        hs, zone = g["hs"], g["zone"]
        out.append({
            "zone_id": zone["id"], "zone_name": zone["name"], "province": zone["province"],
            "lat": sum(h["lat"] for h in hs) / len(hs),
            "lon": sum(h["lon"] for h in hs) / len(hs),
            "count": len(hs),
            "frp_sum": sum(h["frp"] for h in hs),
            "ids": {h["id"] for h in hs},
        })
    out.sort(key=lambda c: -c["frp_sum"])
    return out
