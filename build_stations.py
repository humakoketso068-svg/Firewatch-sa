"""
Turn a spreadsheet of fire stations into stations.json (run it next to main.py).

    python build_stations.py stations.csv

Columns (header row required, extra columns are ignored):
    name, province, lat, lon, phone, sms, email, area, verified, source

  name      e.g. "Komatipoort Fire & Rescue"
  lat, lon  decimal degrees, e.g. -25.4333 and 31.9500 (get them from the station's map pin)
  phone     the public switchboard / control-room number (shown to people, never texted)
  sms       a mobile number that RECEIVES TEXT MESSAGES. Only fill this in after the station told you
            it wants Firewatch alerts there. Many fire stations have no SMS line.
  email     a mailbox the station reads, again only with their agreement
  area      the area they cover, e.g. "Komatipoort, Malelane, Kruger south gate"
  verified  yes ONLY after someone at Firewatch phoned or emailed the station and confirmed the details
  source    where you got the details (municipal website, phone call on 14 Nov, ...)

Firewatch only sends SOS messages to stations that are verified AND have an sms or email.
Everything else is listed for information and the caller is told to dial 112.
"""

import csv
import io
import json
import re
import sys
from pathlib import Path

SA_BOUNDS = (-35.2, 16.3, -21.9, 33.1)          # south, west, north, east
PHONE = re.compile(r"^\+?[0-9 ()\-]{7,20}$")


def convert(csv_text):
    """Returns (stations, problems). Rows with a problem are skipped and reported."""
    stations, problems = [], []
    for n, row in enumerate(csv.DictReader(io.StringIO(csv_text)), start=2):
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
        label = row.get("name") or f"row {n}"
        try:
            lat, lon = float(row["lat"]), float(row["lon"])
        except (KeyError, ValueError):
            problems.append(f"{label}: lat/lon missing or not numbers")
            continue
        s, w, nn, e = SA_BOUNDS
        if not (s <= lat <= nn and w <= lon <= e):
            problems.append(f"{label}: coordinates are outside South Africa (swapped lat/lon?)")
            continue
        if not row.get("name"):
            problems.append(f"row {n}: no name")
            continue
        for field in ("phone", "sms"):
            if row.get(field) and not PHONE.match(row[field]):
                problems.append(f"{label}: {field} '{row[field]}' does not look like a phone number")
                row[field] = ""
        verified = row.get("verified", "").lower() in ("yes", "y", "true", "1")
        if verified and not row.get("source"):
            problems.append(f"{label}: marked verified but no source given, so it is saved as NOT verified")
            verified = False
        stations.append({
            "id": re.sub(r"[^a-z0-9]+", "-", row["name"].lower()).strip("-") or f"st-{n}",
            "name": row["name"], "province": row.get("province", ""), "lat": lat, "lon": lon,
            "phone": row.get("phone", ""), "sms": row.get("sms", ""), "email": row.get("email", ""),
            "area": row.get("area", ""), "verified": verified, "source": row.get("source", ""),
        })
    return stations, problems


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    src = Path(sys.argv[1])
    stations, problems = convert(src.read_text(encoding="utf-8-sig"))
    out = Path(__file__).resolve().parent / "stations.json"
    out.write_text(json.dumps(stations, indent=1, ensure_ascii=False), encoding="utf-8")
    ok = sum(1 for s in stations if s["verified"] and (s["sms"] or s["email"]))
    print(f"Wrote {len(stations)} stations to {out.name}: {ok} can receive SOS messages, "
          f"{sum(1 for s in stations if s['verified'])} verified.")
    for p in problems:
        print("  problem:", p)


if __name__ == "__main__":
    main()
