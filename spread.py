"""
Indicative fire-spread projection: where a fire could reach in the next few hours.

A simple elliptical-growth model (the shape used by fire agencies for grass and savanna
fires): the head of the fire runs downwind, the flanks and back spread slower. Inputs are
wind speed and direction, fuel moisture and slope. It is NOT an operational model: real
fires depend on fuel type, firefighting and terrain detail that are not available here.
Always shown as "indicative" in the app.

Directions are compass bearings the wind blows TOWARD (0 = north, 90 = east), the same
way the arrow on the map compass points.
"""

import math

import weather

KM_PER_DEG_LAT = 111.0


def fuel_moisture(temp_c, humidity):
    """Equilibrium moisture content (%) of fine dead fuel from air temperature and relative
    humidity (Simard 1968, as used in the Fosberg fire-weather index)."""
    t_f = temp_c * 9 / 5 + 32
    h = max(0.0, min(100.0, humidity))
    if h < 10:
        m = 0.03229 + 0.281073 * h - 0.000578 * h * t_f
    elif h < 50:
        m = 2.22749 + 0.160107 * h - 0.014784 * t_f
    else:
        m = 21.0606 + 0.005565 * h * h - 0.00035 * h * t_f - 0.483199 * h
    return max(2.0, min(30.0, m))


def predict(wind_kmh, toward_deg, moisture, slope=0.0, hours=3.0):
    """Ellipse the fire may cover after `hours`, or None when conditions give almost no spread.
    Returns dict: ros_kmh (head rate of spread), head_km, a_km / b_km (half length / half
    width), centre_km (distance of the ellipse centre from the ignition point, downwind),
    bearing, hours, area_ha."""
    wind = max(0.0, float(wind_kmh))
    moisture = float(moisture)
    slope = max(0.0, min(1.0, float(slope or 0)))
    moisture_factor = max(0.05, 1 - moisture / 25.0)           # damp fuel barely burns
    wind_factor = 1 + 0.9 * (wind / 10.0) ** 1.4
    slope_factor = 1 + 1.5 * slope
    ros = 0.6 * moisture_factor * wind_factor * slope_factor
    if ros < 0.05:
        return None
    u_mph = wind / 1.609
    lb = 0.936 * math.exp(0.2566 * u_mph) + 0.461 * math.exp(-0.1548 * u_mph) - 0.397
    lb = max(1.0, min(6.0, lb))                                  # length-to-breadth ratio
    ecc = math.sqrt(max(0.0, 1 - 1 / (lb * lb)))
    head = ros * hours
    a = head / (1 + ecc)
    b = a / lb
    return {
        "ros_kmh": ros, "head_km": head, "a_km": a, "b_km": b, "centre_km": a * ecc,
        "bearing": float(toward_deg) % 360, "hours": hours,
        "area_ha": math.pi * a * b * 100,
    }


def offset(lat, lon, bearing, km):
    """Point `km` away from (lat, lon) along a compass bearing."""
    br = math.radians(bearing)
    dlat = km * math.cos(br) / KM_PER_DEG_LAT
    dlon = km * math.sin(br) / (KM_PER_DEG_LAT * max(0.2, math.cos(math.radians(lat))))
    return lat + dlat, lon + dlon


def for_fire(fire, state, hours=3.0):
    """Projection for one fire in the app state. Uses the real forecast for live NASA fires
    when the server has fetched it, otherwise the simulated wind and the zone's moisture.
    Returns (prediction or None, source label)."""
    wx = None
    if fire.get("lat") is not None and fire.get("lon") is not None:
        wx = weather.cached(fire["lat"], fire["lon"])
    if wx:
        moisture = fuel_moisture(wx["temp_c"], wx["humidity"])
        zone = next((z for z in state["zones"] if z["id"] == fire["zone_id"]), None)
        slope = zone["slope"] if zone else 0.0
        return (predict(wx["wind_kmh"], wx["wind_to"], moisture, slope, hours),
                "forecast wind, humidity and temperature (Open-Meteo)")
    zone = next((z for z in state["zones"] if z["id"] == fire["zone_id"]), None)
    if not zone:
        return None, ""
    return (predict(state["wind"]["speed"], state["wind"]["dir"], zone["moisture"], zone["slope"], hours),
            "simulated weather")
