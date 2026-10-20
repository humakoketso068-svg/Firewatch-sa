"""
Fire stations for the emergency dispatch feature.

Stations are generated from the sensor-node towns (one station each) plus a few
extra stations in the big metros. Positions and names are ILLUSTRATIVE: they are
not an official register. Replace build_stations() with a real dataset
(e.g. municipal open data) before relying on this for anything real.
"""

import json
import math
from pathlib import Path

from geo import project
from simulation import ZONE_DEFS

# (town, station suffix, lat offset, lon offset)
METRO_EXTRAS = [
    ("Cape Town", "North", 0.09, 0.03), ("Cape Town", "South", -0.08, 0.02),
    ("Cape Town", "Atlantic", 0.03, -0.03),
    ("Johannesburg", "North", 0.10, 0.00), ("Johannesburg", "South", -0.10, 0.02),
    ("Johannesburg", "East", 0.00, 0.12),
    ("Pretoria", "East", 0.01, 0.10), ("Pretoria", "West", 0.00, -0.10),
    ("Durban", "North", 0.10, 0.02), ("Durban", "South", -0.10, -0.02),
    ("Gqeberha", "North", 0.07, 0.00), ("Bloemfontein", "East", 0.00, 0.08),
]


def _short(name):
    return name.split(" (")[0]


def build_stations():
    stations = []
    by_name = {}
    for zid, name, province, lat, lon, *_ in ZONE_DEFS:
        base = _short(name)
        by_name[base] = (province, lat, lon)
        s_lat, s_lon = lat + 0.012, lon - 0.012
        x, y = project(s_lat, s_lon)
        stations.append({
            "id": f"fs-{zid}", "name": f"{base} Fire & Rescue", "province": province,
            "lat": s_lat, "lon": s_lon, "x": x, "y": y,
        })
    for town, suffix, dlat, dlon in METRO_EXTRAS:
        province, lat, lon = by_name[town]
        s_lat, s_lon = lat + dlat, lon + dlon
        x, y = project(s_lat, s_lon)
        stations.append({
            "id": f"fs-{town}-{suffix}".replace(" ", ""),
            "name": f"{town} {suffix} Fire Station", "province": province,
            "lat": s_lat, "lon": s_lon, "x": x, "y": y,
        })
    return stations


def _load_directory():
    """stations.json next to this file: a list of real stations (see tools/build_stations.py).
    Each entry: id, name, province, lat, lon, and optionally phone, sms, email, area, verified."""
    try:
        data = json.loads((Path(__file__).resolve().parent / "stations.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    out = []
    for i, d in enumerate(data if isinstance(data, list) else []):
        try:
            lat, lon = float(d["lat"]), float(d["lon"])
            x, y = project(lat, lon)
            out.append({
                "id": str(d.get("id") or f"st-{i}"), "name": str(d["name"]),
                "province": str(d.get("province", "")), "lat": lat, "lon": lon, "x": x, "y": y,
                "phone": str(d.get("phone", "")), "sms": str(d.get("sms", "")),
                "email": str(d.get("email", "")), "area": str(d.get("area", "")),
                "verified": bool(d.get("verified", False)),
            })
        except (KeyError, TypeError, ValueError):
            continue
    return out


_REAL = _load_directory()
USING_REAL_DIRECTORY = bool(_REAL)
FIRE_STATIONS = _REAL or build_stations()    # without stations.json these are ILLUSTRATIVE samples


def contactable(station):
    """A station we may message directly: confirmed by a human and with an SMS number or email."""
    return bool(station.get("verified") and (station.get("sms") or station.get("email")))


def distance_km(lat1, lon1, lat2, lon2):
    """Great-circle distance (haversine)."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def nearby_stations(lat, lon, radius_km=100, min_count=3, max_count=10):
    """All stations within radius_km (nearest first). Always returns at least
    min_count so a remote location still reaches the closest crews."""
    ranked = sorted(
        ((s, distance_km(lat, lon, s["lat"], s["lon"])) for s in FIRE_STATIONS),
        key=lambda item: item[1],
    )
    chosen = [item for item in ranked if item[1] <= radius_km][:max_count]
    if len(chosen) < min_count:
        chosen = ranked[:min_count]
    return chosen


def eta_minutes(km):
    """Rough response time: 4 min turn-out plus travel at ~70 km/h."""
    return max(4, round(4 + km / 70 * 60))
