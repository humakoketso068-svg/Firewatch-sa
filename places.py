"""
Real place names and exact coordinates for South Africa (cities, towns, townships,
suburbs, villages, rural settlements), read from places.json.

places.json is built from the GeoNames gazetteer by `python tools/build_places.py`
(see SETUP_LIVE_FEATURES.md). If the file is missing the app still works; the map just
has the 83 sensor towns, and `available()` is False.
"""

import json
import math
from pathlib import Path

FILE = Path(__file__).resolve().parent / "places.json"
CELL = 0.25                      # degrees per grid cell for the spatial index
ATTRIBUTION = "Place names: GeoNames (CC BY 4.0)"

_loaded = False
_places = []                     # [name, lat, lon, province index, population, code]
_provinces = []
_grid = {}


def _load():
    global _loaded, _places, _provinces, _grid
    if _loaded:
        return
    _loaded = True
    try:
        data = json.loads(FILE.read_text(encoding="utf-8"))
        _places, _provinces = data["places"], data["provinces"]
    except (OSError, ValueError, KeyError, TypeError):
        _places, _provinces = [], []
    _grid = {}
    for i, p in enumerate(_places):
        _grid.setdefault((math.floor(p[1] / CELL), math.floor(p[2] / CELL)), []).append(i)


def available():
    _load()
    return bool(_places)


def count():
    _load()
    return len(_places)


def as_dict(p):
    return {"name": p[0], "lat": p[1], "lon": p[2],
            "province": _provinces[p[3]] if 0 <= p[3] < len(_provinces) else "",
            "pop": p[4], "code": p[5]}


def search(query, limit=8):
    """Places whose name starts with, or has a word starting with, the query.
    Bigger places first. Returns dicts."""
    _load()
    q = " ".join((query or "").lower().split())
    if len(q) < 2:
        return []
    starts, words, inside = [], [], []
    for p in _places:                               # already sorted by population
        name = p[0].lower()
        if name.startswith(q):
            starts.append(p)
        elif (" " + q) in name or ("-" + q) in name:
            words.append(p)
        elif len(q) >= 4 and q in name:
            inside.append(p)
        if len(starts) >= limit and len(words) + len(starts) >= limit * 3:
            break
    return [as_dict(p) for p in (starts + words + inside)[:limit]]


def distance_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _cells(south, west, north, east):
    for ci in range(math.floor(south / CELL), math.floor(north / CELL) + 1):
        for cj in range(math.floor(west / CELL), math.floor(east / CELL) + 1):
            yield ci, cj


def in_view(south, west, north, east, limit=80):
    """Biggest places inside a lat/lon box (for map labels)."""
    _load()
    if not _places or (north - south) * (east - west) > 60:
        return []
    found = []
    for cell in _cells(south, west, north, east):
        for i in _grid.get(cell, ()):
            p = _places[i]
            if south <= p[1] <= north and west <= p[2] <= east:
                found.append(i)
    found.sort()                                     # index order = population order
    return [as_dict(_places[i]) for i in found[:limit]]


def nearest(lat, lon, max_km=25.0):
    """The closest named place to a point, with its distance. (dict, km) or (None, None)."""
    _load()
    if not _places:
        return None, None
    best, best_km = None, max_km
    span = max(1, math.ceil(max_km / 111.0 / CELL))
    ci, cj = math.floor(lat / CELL), math.floor(lon / CELL)
    for di in range(-span, span + 1):
        for dj in range(-span, span + 1):
            for i in _grid.get((ci + di, cj + dj), ()):
                p = _places[i]
                km = distance_km(lat, lon, p[1], p[2])
                if km < best_km:
                    best, best_km = p, km
    return (as_dict(best), best_km) if best else (None, None)


_COMPASS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")


def bearing_name(lat1, lon1, lat2, lon2):
    """Compass direction from point 1 to point 2, e.g. 'NE'."""
    y = math.sin(math.radians(lon2 - lon1)) * math.cos(math.radians(lat2))
    x = (math.cos(math.radians(lat1)) * math.sin(math.radians(lat2))
         - math.sin(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.cos(math.radians(lon2 - lon1)))
    deg = (math.degrees(math.atan2(y, x)) + 360) % 360
    return _COMPASS[int((deg + 22.5) // 45) % 8]


_where_cache = {}


def where(lat, lon, max_km=40.0):
    """'12 km NE of Lerome, Limpopo' for any point, or '' if no place data / nothing near."""
    key = (round(lat, 3), round(lon, 3))
    if key in _where_cache:
        return _where_cache[key]
    place, km = nearest(lat, lon, max_km)
    if not place:
        text = ""
    else:
        name = place.get("name", "")
        prov = place.get("province", "")
        tail = f", {prov}" if prov else ""
        if km < 2:
            text = f"at {name}{tail}"
        else:
            text = f"{km:.0f} km {bearing_name(place['lat'], place['lon'], lat, lon)} of {name}{tail}"
    if len(_where_cache) > 5000:
        _where_cache.clear()
    _where_cache[key] = text
    return text
