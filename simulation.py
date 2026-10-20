

import random
from datetime import datetime

from geo import project

ZONE_DEFS = [
    # id, name, province, lat, lon, elev, slope
    # lat/lon are converted to map x/y by geo.project().
    # -- Western Cape ----------------------------------------------
    ("z1", "Cape Town", "Western Cape", -33.92, 18.42, 0.10, 0.45),
    ("z2", "Stellenbosch", "Western Cape", -33.93, 18.86, 0.20, 0.50),
    ("z3", "Paarl", "Western Cape", -33.73, 18.96, 0.20, 0.45),
    ("z4", "Franschhoek", "Western Cape", -33.91, 19.12, 0.30, 0.70),
    ("z5", "Hermanus", "Western Cape", -34.42, 19.24, 0.10, 0.50),
    ("z6", "Worcester", "Western Cape", -33.65, 19.45, 0.25, 0.40),
    ("z7", "Clanwilliam (Cederberg)", "Western Cape", -32.18, 18.89, 0.30, 0.70),
    ("z8", "Saldanha", "Western Cape", -33.01, 17.94, 0.05, 0.10),
    ("z9", "Bredasdorp", "Western Cape", -34.53, 20.04, 0.10, 0.15),
    ("z10", "Swellendam", "Western Cape", -34.02, 20.44, 0.20, 0.50),
    ("z11", "Laingsburg", "Western Cape", -33.20, 20.86, 0.35, 0.35),
    ("z12", "Oudtshoorn", "Western Cape", -33.59, 22.20, 0.30, 0.45),
    ("z13", "Mossel Bay", "Western Cape", -34.18, 22.14, 0.05, 0.15),
    ("z14", "George", "Western Cape", -33.96, 22.46, 0.15, 0.40),
    ("z15", "Knysna", "Western Cape", -34.04, 23.05, 0.10, 0.55),
    ("z16", "Beaufort West", "Western Cape", -32.35, 22.58, 0.55, 0.30),
    # -- Eastern Cape ----------------------------------------------
    ("z17", "Gqeberha", "Eastern Cape", -33.96, 25.60, 0.05, 0.15),
    ("z18", "Jeffreys Bay", "Eastern Cape", -34.05, 24.92, 0.05, 0.20),
    ("z19", "Makhanda", "Eastern Cape", -33.31, 26.52, 0.40, 0.45),
    ("z20", "East London", "Eastern Cape", -33.02, 27.91, 0.05, 0.25),
    ("z21", "Komani", "Eastern Cape", -31.90, 26.88, 0.55, 0.40),
    ("z22", "Graaff-Reinet", "Eastern Cape", -32.25, 24.53, 0.45, 0.40),
    ("z23", "Aliwal North", "Eastern Cape", -30.69, 26.71, 0.60, 0.25),
    ("z24", "Mthatha", "Eastern Cape", -31.59, 28.78, 0.40, 0.55),
    ("z25", "Port St Johns", "Eastern Cape", -31.62, 29.54, 0.05, 0.70),
    # -- Free State ------------------------------------------------
    ("z26", "Bloemfontein", "Free State", -29.12, 26.21, 0.55, 0.15),
    ("z27", "Welkom", "Free State", -27.98, 26.73, 0.55, 0.10),
    ("z28", "Kroonstad", "Free State", -27.65, 27.23, 0.55, 0.15),
    ("z29", "Bethlehem", "Free State", -28.23, 28.31, 0.65, 0.40),
    ("z30", "Harrismith", "Free State", -28.27, 29.13, 0.65, 0.55),
    ("z31", "Phuthaditjhaba", "Free State", -28.53, 28.82, 0.75, 0.80),
    ("z32", "Parys", "Free State", -26.90, 27.46, 0.55, 0.20),
    # -- Gauteng ---------------------------------------------------
    ("z33", "Johannesburg", "Gauteng", -26.20, 28.05, 0.60, 0.25),
    ("z34", "Pretoria", "Gauteng", -25.75, 28.19, 0.50, 0.35),
    ("z35", "Krugersdorp", "Gauteng", -26.10, 27.77, 0.60, 0.35),
    ("z36", "Vereeniging", "Gauteng", -26.67, 27.93, 0.55, 0.15),
    # -- KwaZulu-Natal ---------------------------------------------
    ("z37", "Durban", "KwaZulu-Natal", -29.86, 31.02, 0.05, 0.30),
    ("z38", "Pietermaritzburg", "KwaZulu-Natal", -29.62, 30.38, 0.30, 0.45),
    ("z39", "Richards Bay", "KwaZulu-Natal", -28.78, 32.04, 0.02, 0.05),
    ("z40", "Ulundi", "KwaZulu-Natal", -28.33, 31.42, 0.25, 0.30),
    ("z41", "Ladysmith", "KwaZulu-Natal", -28.56, 29.78, 0.45, 0.30),
    ("z42", "Newcastle", "KwaZulu-Natal", -27.76, 29.93, 0.55, 0.35),
    ("z43", "Vryheid", "KwaZulu-Natal", -27.77, 30.79, 0.45, 0.40),
    ("z44", "Pongola", "KwaZulu-Natal", -27.38, 31.62, 0.15, 0.20),
    ("z45", "Underberg (Drakensberg)", "KwaZulu-Natal", -29.79, 29.50, 0.70, 0.80),
    ("z46", "Kokstad", "KwaZulu-Natal", -30.55, 29.42, 0.55, 0.50),
    # -- Limpopo ---------------------------------------------------
    ("z47", "Polokwane", "Limpopo", -23.90, 29.45, 0.50, 0.15),
    ("z48", "Musina", "Limpopo", -22.34, 30.04, 0.25, 0.15),
    ("z49", "Makhado", "Limpopo", -23.05, 29.90, 0.40, 0.55),
    ("z50", "Thohoyandou", "Limpopo", -22.95, 30.48, 0.35, 0.50),
    ("z51", "Tzaneen", "Limpopo", -23.83, 30.16, 0.35, 0.60),
    ("z52", "Phalaborwa", "Limpopo", -23.94, 31.14, 0.15, 0.20),
    ("z53", "Mokopane", "Limpopo", -24.19, 29.01, 0.45, 0.25),
    ("z54", "Lephalale", "Limpopo", -23.67, 27.74, 0.30, 0.15),
    ("z55", "Bela-Bela", "Limpopo", -24.88, 28.29, 0.45, 0.20),
    # -- Mpumalanga ------------------------------------------------
    ("z56", "Mbombela", "Mpumalanga", -25.47, 30.98, 0.25, 0.45),
    ("z57", "Sabie", "Mpumalanga", -25.10, 30.78, 0.40, 0.75),
    ("z58", "Graskop", "Mpumalanga", -24.94, 30.85, 0.50, 0.75),
    ("z59", "Mashishing", "Mpumalanga", -25.10, 30.45, 0.55, 0.60),
    ("z60", "Barberton", "Mpumalanga", -25.79, 31.05, 0.30, 0.70),
    ("z61", "Komatipoort", "Mpumalanga", -25.43, 31.95, 0.10, 0.10),
    ("z62", "Skukuza (Kruger)", "Mpumalanga", -24.99, 31.59, 0.15, 0.15),
    ("z63", "eMalahleni", "Mpumalanga", -25.87, 29.23, 0.55, 0.15),
    ("z64", "Secunda", "Mpumalanga", -26.55, 29.17, 0.60, 0.10),
    ("z65", "Ermelo", "Mpumalanga", -26.53, 29.98, 0.65, 0.20),
    # -- North West ------------------------------------------------
    ("z66", "Mahikeng", "North West", -25.86, 25.64, 0.45, 0.10),
    ("z67", "Zeerust", "North West", -25.54, 26.08, 0.45, 0.30),
    ("z68", "Rustenburg", "North West", -25.67, 27.24, 0.45, 0.40),
    ("z69", "Brits", "North West", -25.63, 27.78, 0.40, 0.25),
    ("z70", "Potchefstroom", "North West", -26.72, 27.10, 0.55, 0.10),
    ("z71", "Klerksdorp", "North West", -26.85, 26.67, 0.50, 0.10),
    ("z72", "Vryburg", "North West", -26.96, 24.73, 0.50, 0.10),
    # -- Northern Cape ---------------------------------------------
    ("z73", "Kimberley", "Northern Cape", -28.74, 24.77, 0.55, 0.10),
    ("z74", "Upington", "Northern Cape", -28.45, 21.26, 0.40, 0.10),
    ("z75", "Springbok", "Northern Cape", -29.66, 17.89, 0.35, 0.55),
    ("z76", "Port Nolloth", "Northern Cape", -29.25, 16.87, 0.02, 0.05),
    ("z77", "Kuruman", "Northern Cape", -27.45, 23.43, 0.55, 0.20),
    ("z78", "Postmasburg", "Northern Cape", -28.33, 23.06, 0.55, 0.35),
    ("z79", "Prieska", "Northern Cape", -29.66, 22.75, 0.45, 0.15),
    ("z80", "De Aar", "Northern Cape", -30.65, 24.01, 0.60, 0.15),
    ("z81", "Calvinia", "Northern Cape", -31.47, 19.78, 0.50, 0.40),
    ("z82", "Sutherland", "Northern Cape", -32.40, 20.66, 0.70, 0.30),
    ("z83", "Twee Rivieren (Kgalagadi)", "Northern Cape", -26.47, 20.61, 0.40, 0.05),
]

MAX_HISTORY = 60
MAX_FEED = 60
TICK_SECONDS = 2.2

# The original demo had 12 nodes. Scale ignition odds so a bigger network
# doesn't produce a proportionally bigger number of fires.
IGNITION_SCALE = 12 / len(ZONE_DEFS)


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


class Simulation:
    def __init__(self):
        self.zones = []
        for zid, name, province, lat, lon, elev, slope in ZONE_DEFS:
            x, y = project(lat, lon)
            self.zones.append({
                "id": zid, "name": name, "province": province,
                "lat": lat, "lon": lon, "x": x, "y": y,
                "elev": elev, "slope": slope,
                "temp": 78 + random.random() * 10,
                "humidity": 25 + random.random() * 20,
                "moisture": 8 + random.random() * 10,
                "risk": 0.0, "risk_level": "low", "on_fire": False,
            })
        self.wind_speed = 19 + random.random() * 13        # km/h
        self.wind_dir = random.random() * 360
        self.wind_history = []
        self.moist_history = []
        self.fires = []
        self.feed = []
        self.tick_count = 0
        self.fire_id_seq = 1
        self.live_mode = False      # True: fires come from NASA FIRMS, not the simulation

        # seed some history so the first snapshot isn't empty
        for _ in range(20):
            self._step_environment()
        self._log("info", "System",
                  f"Sensor network initialized — {len(self.zones)} nodes online across South Africa's nine provinces.")

    # -- risk model ---------------------------------------------------
    def _compute_risk(self, z):
        wind_term = min(self.wind_speed / 56, 1)
        moist_term = 1 - min(z["moisture"] / 20, 1)
        temp_term = min((z["temp"] - 60) / 40, 1)
        slope_term = z["slope"]
        score = wind_term * 0.28 + moist_term * 0.34 + temp_term * 0.2 + slope_term * 0.18
        return clamp(score, 0, 1)

    @staticmethod
    def _risk_level(score):
        if score > 0.72:
            return "extreme"
        if score > 0.52:
            return "high"
        if score > 0.32:
            return "moderate"
        return "low"

    def _log(self, cls, tag, text):
        """cls: 'extreme' | 'high' | 'info' | 'contained'. Use [b]..[/b] for emphasis."""
        ts = datetime.now().strftime("%H:%M:%S")
        self.feed.append({"cls": cls, "tag": tag, "text": text, "ts": ts})
        if len(self.feed) > MAX_FEED:
            self.feed.pop(0)

    def log_event(self, cls, tag, text):
        """Public wrapper so the UI can add entries (e.g. emergency alerts) to the feed."""
        self._log(cls, tag, text)

    # -- simulation steps ----------------------------------------------
    def _step_environment(self):
        self.wind_speed = clamp(self.wind_speed + (random.random() - 0.5) * 3.5, 6, 68)
        self.wind_dir = (self.wind_dir + (random.random() - 0.5) * 10 + 360) % 360

        for z in self.zones:
            z["temp"] = clamp(z["temp"] + (random.random() - 0.5) * 1.4, 55, 108)
            z["humidity"] = clamp(z["humidity"] + (random.random() - 0.5) * 2, 5, 70)
            dry_pull = -0.15 if z["on_fire"] else -0.02
            z["moisture"] = clamp(z["moisture"] + (random.random() - 0.5) * 0.6 + dry_pull, 2, 26)
            z["risk"] = self._compute_risk(z)
            z["risk_level"] = self._risk_level(z["risk"])

        avg_moist = sum(z["moisture"] for z in self.zones) / len(self.zones)
        self.wind_history.append(self.wind_speed)
        if len(self.wind_history) > MAX_HISTORY:
            self.wind_history.pop(0)
        self.moist_history.append(avg_moist)
        if len(self.moist_history) > MAX_HISTORY:
            self.moist_history.pop(0)

    def _maybe_ignite(self):
        if self.live_mode:
            return
        for z in self.zones:
            if z["on_fire"]:
                continue
            chance = (z["risk"] ** 3) * 0.05 * IGNITION_SCALE
            if random.random() < chance:
                self._ignite(z)

    def _ignite(self, z):
        z["on_fire"] = True
        self.fires.append({
            "id": self.fire_id_seq, "zone_id": z["id"], "zone_name": z["name"], "province": z["province"],
            "x": z["x"], "y": z["y"], "start_tick": self.tick_count,
            "radius": 3.0, "max_radius": 12 + z["risk"] * 28,
            "wind_dir_at_start": self.wind_dir, "severity": z["risk_level"],
            "contained": False, "contain_tick": None,
        })
        self.fire_id_seq += 1
        self._log(
            "extreme" if z["risk_level"] == "extreme" else "high",
            "Detection",
            f"New smoke/heat signature confirmed at [b]{z['name']}[/b], {z['province']} — "
            f"risk level {z['risk_level'].upper()}.",
        )

    def _step_fires(self):
        for f in self.fires:
            if f["contained"]:
                continue
            age = self.tick_count - f["start_tick"]
            growth = f["max_radius"] / 22
            f["radius"] = min(f["max_radius"], f["radius"] + growth)
            f["wind_dir_at_start"] = self.wind_dir  # spread axis follows current wind

            if f["radius"] >= f["max_radius"] and random.random() < 0.35:
                f["contained"] = True
                f["contain_tick"] = self.tick_count
                zone = next((zz for zz in self.zones if zz["id"] == f["zone_id"]), None)
                if zone:
                    zone["on_fire"] = False
                self._log("contained", "Containment",
                          f"Fire at [b]{f['zone_name']}[/b] reported contained by ground crews.")
            elif age > 0 and age % 6 == 0:
                self._log("info", "Update",
                          f"Fire at [b]{f['zone_name']}[/b] spreading — radius {round(f['radius'])} units, "
                          f"wind {round(self.wind_speed)} km/h.")

        self.fires = [
            f for f in self.fires
            if not f["contained"] or (self.tick_count - f["contain_tick"]) < 40
        ]

    def tick(self):
        self.tick_count += 1
        self._step_environment()
        if self.live_mode:
            return                      # real fires are pushed in by set_live_fires()
        self._maybe_ignite()
        self._step_fires()

    # -- live (NASA FIRMS) mode ------------------------------------------
    def set_live(self, flag):
        """Switch between simulated fires and real satellite detections."""
        self.live_mode = bool(flag)
        self.fires = []
        for z in self.zones:
            z["on_fire"] = False

    def set_live_fires(self, clusters):
        """clusters come from firms.cluster(): one entry per town with hotspots near it."""
        by_id = {z["id"]: z for z in self.zones}
        for z in self.zones:
            z["on_fire"] = False
        fires = []
        for i, c in enumerate(clusters, start=1):
            x, y = project(c["lat"], c["lon"])
            n, power = c["count"], c["frp_sum"]
            severity = "extreme" if (n >= 8 or power >= 300) else "high" if (n >= 3 or power >= 80) else "moderate"
            radius = 3.0 + min(n, 15) * 0.9
            fires.append({
                "id": i, "zone_id": c["zone_id"], "zone_name": c["zone_name"], "province": c["province"],
                "x": x, "y": y, "lat": c["lat"], "lon": c["lon"], "start_tick": self.tick_count,
                "radius": radius, "max_radius": radius,
                "wind_dir_at_start": self.wind_dir, "severity": severity,
                "contained": False, "contain_tick": None,
            })
            by_id[c["zone_id"]]["on_fire"] = True
        self.fires = fires

    def snapshot(self):
        top_zone = max(self.zones, key=lambda z: z["risk"])
        return {
            "tick": self.tick_count,
            "server_time": datetime.now().strftime("%H:%M:%S"),
            "zones": self.zones,
            "wind": {"speed": self.wind_speed, "dir": self.wind_dir},
            "wind_history": self.wind_history,
            "moist_history": self.moist_history,
            "fires": self.fires,
            "feed": list(reversed(self.feed[-25:])),
            "top_zone_id": top_zone["id"],
        }
