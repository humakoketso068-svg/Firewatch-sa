"""
Nearby hospitals and assembly points from OpenStreetMap (Overpass API), server only.
Returns whatever volunteers have mapped, so it can be incomplete: always shown with a
"confirm locally" note and a link to a live map search as the fallback.
"""

import json
import threading
import time
import urllib.parse
import urllib.request

import config
from stations import distance_km

_cache = {}
_lock = threading.Lock()


def _query(lat, lon, km):
    r = int(km * 1000)
    return (f"[out:json][timeout:20];("
            f"nwr(around:{r},{lat},{lon})[amenity=hospital];"
            f"nwr(around:{r},{lat},{lon})[emergency=assembly_point];"
            f");out center 60;")


def find(lat, lon, km=30):
    """{'hospitals': [...], 'assembly': [...]} sorted by distance, or None if unavailable."""
    if config.IN_BROWSER:
        return None
    key = (round(lat, 2), round(lon, 2))
    with _lock:
        hit = _cache.get(key)
        if hit and time.time() - hit[0] < 6 * 3600:
            return hit[1]
    try:
        url = "https://overpass-api.de/api/interpreter?data=" + urllib.parse.quote(_query(lat, lon, km))
        req = urllib.request.Request(url, headers={"User-Agent": "Firewatch/1.0"})
        with urllib.request.urlopen(req, timeout=25) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None
    out = {"hospitals": [], "assembly": []}
    for el in data.get("elements", []):
        tags = el.get("tags", {})
        la = el.get("lat") or (el.get("center") or {}).get("lat")
        lo = el.get("lon") or (el.get("center") or {}).get("lon")
        if la is None or lo is None:
            continue
        item = {"name": tags.get("name") or ("Hospital" if tags.get("amenity") == "hospital" else "Assembly point"),
                "lat": la, "lon": lo, "km": distance_km(lat, lon, la, lo), "phone": tags.get("phone", "")}
        (out["hospitals"] if tags.get("amenity") == "hospital" else out["assembly"]).append(item)
    for k in out:
        out[k].sort(key=lambda i: i["km"])
        out[k] = out[k][:4]
    with _lock:
        _cache[key] = (time.time(), out)
    return out


def map_search_link(what, lat, lon):
    return f"https://www.google.com/maps/search/{urllib.parse.quote(what)}/@{lat:.5f},{lon:.5f},13z"


def directions_link(lat, lon):
    return f"https://www.google.com/maps/dir/?api=1&destination={lat:.5f},{lon:.5f}"
