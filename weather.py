"""
Real weather for active fires from Open-Meteo (free, no key), server only.

The background monitor calls fetch() for each fire after a NASA refresh. The map only
ever reads cached(), so drawing never waits on the network.
"""

import json
import threading
import time
import urllib.request

import config

CELL = 0.25                 # degrees: nearby fires share one forecast
TTL = 45 * 60
_cache = {}
_lock = threading.Lock()


def _key(lat, lon):
    return (round(lat / CELL), round(lon / CELL))


def cached(lat, lon):
    """Most recent weather for this spot, or None. Never touches the network."""
    with _lock:
        hit = _cache.get(_key(lat, lon))
    if hit and time.time() - hit[0] < TTL * 3:
        return hit[1]
    return None


def parse(data):
    cur = data["current"]
    return {
        "temp_c": float(cur["temperature_2m"]),
        "humidity": float(cur["relative_humidity_2m"]),
        "wind_kmh": float(cur["wind_speed_10m"]),
        "wind_to": (float(cur["wind_direction_10m"]) + 180) % 360,      # API gives where it blows FROM
    }


def fetch(lat, lon):
    """Download and cache the weather for a spot. Returns the weather or None."""
    if config.IN_BROWSER:
        return None
    key = _key(lat, lon)
    with _lock:
        hit = _cache.get(key)
        if hit and time.time() - hit[0] < TTL:
            return hit[1]
    url = ("https://api.open-meteo.com/v1/forecast?latitude=%.3f&longitude=%.3f&wind_speed_unit=kmh"
           "&current=temperature_2m,relative_humidity_2m,wind_speed_10m,wind_direction_10m" % (lat, lon))
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Firewatch/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            wx = parse(json.loads(resp.read().decode("utf-8")))
    except Exception:
        return None
    with _lock:
        _cache[key] = (time.time(), wx)
    return wx
