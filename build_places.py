"""
Build places.json: every named place in South Africa (cities, towns, townships,
suburbs, villages and rural settlements) with its exact coordinates and province.

Run this ONCE on your own computer (it needs internet), from the project folder:

    python build_places.py        (or: python tools/build_places.py)

It downloads the free GeoNames gazetteer for South Africa (https://www.geonames.org,
licence CC BY 4.0) and writes places.json next to main.py. Commit that file to git so
Render and Netlify have it. Re-run it any time you want fresher data.

Options:
    --min-pop N     keep only places with at least N people (default 0 = everything)
    --zip PATH      use an already downloaded ZA.zip instead of downloading
    --admin PATH    use an already downloaded admin1CodesASCII.txt
"""

import argparse
import io
import json
import re
import sys
import urllib.request
import zipfile
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
# Works from the project folder (next to main.py) or from a tools/ subfolder.
ROOT = HERE if (HERE / "main.py").exists() else HERE.parent
sys.path.insert(0, str(ROOT))

DUMP = "https://download.geonames.org/export/dump/"
PROVINCES = ["Eastern Cape", "Free State", "Gauteng", "KwaZulu-Natal", "Limpopo",
             "Mpumalanga", "North West", "Northern Cape", "Western Cape"]
_CANON = {re.sub(r"[^a-z]", "", p.lower()): p for p in PROVINCES}
_CANON["northwestprovince"] = "North West"


def canon_province(name):
    return _CANON.get(re.sub(r"[^a-z]", "", (name or "").lower()))


def download(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Firewatch place builder"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.read()


def read_admin1(text):
    """admin1CodesASCII.txt -> {'ZA.01': 'Eastern Cape', ...}"""
    out = {}
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2 and parts[0].startswith("ZA."):
            out[parts[0]] = canon_province(parts[1]) or canon_province(parts[2] if len(parts) > 2 else "")
    return out


def build(zip_bytes, admin_text, min_pop=0):
    """Returns (data_dict, stats). Pure function, so it can be tested without internet."""
    from simulation import ZONE_DEFS
    admin = read_admin1(admin_text)
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        raw = zf.read("ZA.txt").decode("utf-8", "replace")

    zone_pts = [(lat, lon, prov) for _, _, prov, lat, lon, *_ in ZONE_DEFS]

    def province_by_nearest_town(lat, lon):
        return min(zone_pts, key=lambda z: (z[0] - lat) ** 2 + (z[1] - lon) ** 2)[2]

    seen, places, stats = set(), [], {"fallback_province": 0}
    for line in raw.splitlines():
        c = line.split("\t")
        if len(c) < 15 or c[6] != "P":              # P = populated places
            continue
        name, code = c[1].strip(), c[7]
        if not name:
            continue
        try:
            lat, lon, pop = float(c[4]), float(c[5]), int(c[14] or 0)
        except ValueError:
            continue
        if pop < min_pop or not (-35.2 <= lat <= -21.9 and 16.3 <= lon <= 33.1):
            continue
        key = (name.lower(), round(lat, 3), round(lon, 3))
        if key in seen:
            continue
        seen.add(key)
        province = admin.get("ZA." + c[10])
        if not province:
            province = province_by_nearest_town(lat, lon)
            stats["fallback_province"] += 1
        places.append([name, round(lat, 5), round(lon, 5), PROVINCES.index(province) if province in PROVINCES else -1,
                       pop, code])
    places.sort(key=lambda p: (-p[4], p[0]))
    data = {"source": "GeoNames (CC BY 4.0), https://www.geonames.org", "built": date.today().isoformat(),
            "provinces": PROVINCES, "places": places}
    stats["total"] = len(places)
    stats["by_province"] = {p: sum(1 for x in places if x[3] == i) for i, p in enumerate(PROVINCES)}
    return data, stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-pop", type=int, default=0)
    ap.add_argument("--zip")
    ap.add_argument("--admin")
    args = ap.parse_args()

    print("Getting South Africa places from GeoNames…")
    zip_bytes = Path(args.zip).read_bytes() if args.zip else download(DUMP + "ZA.zip")
    admin_text = (Path(args.admin).read_text(encoding="utf-8") if args.admin
                  else download(DUMP + "admin1CodesASCII.txt").decode("utf-8", "replace"))
    data, stats = build(zip_bytes, admin_text, args.min_pop)

    out = ROOT / "places.json"
    out.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"\nWrote {out}  ({out.stat().st_size / 1e6:.1f} MB, {stats['total']} places)")
    for prov, n in stats["by_province"].items():
        print(f"  {prov:<15}{n:>7}")
    if stats["fallback_province"]:
        print(f"\n{stats['fallback_province']} places had no province code; their province was taken "
              "from the nearest sensor town.")
    missing = [p for p, n in stats["by_province"].items() if n == 0]
    if missing:
        print("\nWARNING: no places found for:", ", ".join(missing))
    for probe in ("Lerome", "Soweto", "Mogwase"):
        hits = [p for p in data["places"] if p[0].lower().startswith(probe.lower())][:3]
        print(f"  check '{probe}':", [(h[0], h[1], h[2]) for h in hits] or "not found")


if __name__ == "__main__":
    main()
