"""
Geography for the Firewatch South Africa map.

Everything here is plain data plus one projection function, so both the
simulation (which places sensor nodes) and the UI (which draws the outline)
share the same coordinate system.

Map coordinates: a 640 x 460 view with the origin at the bottom-left
(y grows upward). main.py flips y when it draws.
"""

VIEW_W = 640
VIEW_H = 460

# Bounding box of South Africa, in degrees.
LON_MIN = 16.4
LAT_MIN = -35.0

# Pixels per degree. Longitude is scaled by ~cos(28 deg S) so the country
# is not stretched sideways.
PX_PER_LAT = 32.5
PX_PER_LON = 29.0
PAD_X = 80
PAD_Y = 20


def project(lat, lon):
    """Convert latitude / longitude (degrees) to map x, y."""
    x = PAD_X + (lon - LON_MIN) * PX_PER_LON
    y = PAD_Y + (lat - LAT_MIN) * PX_PER_LAT
    return round(x, 1), round(y, 1)


# ---------------------------------------------------------------------------
# Outlines, as (lat, lon) points. Simplified, so it is a stylised map and
# not a survey-grade border.
# ---------------------------------------------------------------------------

# Clockwise from the Orange River mouth: Namibia, Botswana, Zimbabwe and
# Mozambique borders, then the east, south and west coasts.
SA_OUTLINE = [
    # Orange River / Namibia
    (-28.62, 16.45), (-28.75, 17.00), (-28.72, 17.60), (-28.90, 18.50),
    (-28.75, 19.10), (-28.40, 19.95),
    # 20 deg E line north to the Botswana tripoint
    (-24.77, 20.00),
    # Botswana (Nossob / Molopo / Limpopo)
    (-26.80, 20.60), (-26.90, 21.70), (-26.15, 22.50), (-25.90, 23.60),
    (-25.80, 24.70), (-25.60, 25.60), (-24.75, 26.30), (-24.60, 26.85),
    (-23.65, 27.00), (-23.00, 27.90), (-22.50, 28.90),
    # Zimbabwe (Limpopo)
    (-22.18, 29.35), (-22.20, 29.90), (-22.30, 30.90), (-22.40, 31.30),
    # Mozambique (Lebombo)
    (-23.20, 31.55), (-24.40, 31.95), (-25.10, 31.90), (-25.45, 31.95),
    (-26.85, 32.00), (-26.86, 32.89),
    # East coast
    (-27.60, 32.60), (-28.40, 32.40), (-28.80, 32.10), (-29.87, 31.05),
    (-30.75, 30.40), (-31.60, 29.55), (-32.30, 28.60), (-33.02, 27.90),
    (-33.70, 26.60), (-34.00, 25.60), (-34.20, 24.83), (-34.05, 23.40),
    (-34.20, 22.10), (-34.40, 21.30), (-34.83, 20.00),
    # South-west: Cape Peninsula and the west coast
    (-34.60, 19.30), (-34.36, 18.50), (-33.90, 18.45), (-33.30, 18.30),
    (-32.75, 18.00), (-32.30, 18.30), (-31.80, 18.25), (-30.30, 17.30),
    (-29.25, 16.87),
]

# Enclaves drawn on top of the country in the background colour.
LESOTHO = [
    (-29.20, 27.00), (-28.65, 27.90), (-28.60, 28.60), (-29.20, 29.40),
    (-29.90, 29.40), (-30.60, 28.60), (-30.65, 27.70), (-30.20, 27.20),
    (-29.60, 27.00),
]

ESWATINI = [
    (-25.75, 31.10), (-25.95, 31.95), (-26.80, 32.10), (-27.10, 31.90),
    (-27.30, 31.30), (-26.80, 30.80), (-26.20, 30.80),
]

# Faint province names drawn on the map: (name, lat, lon).
PROVINCE_LABELS = [
    ("Western Cape", -33.45, 21.35),
    ("Northern Cape", -29.9, 21.5),
    ("Eastern Cape", -32.4, 26.4),
    ("Free State", -28.6, 26.2),
    ("KwaZulu-Natal", -28.6, 30.6),
    ("North West", -26.3, 25.5),
    ("Mpumalanga", -25.9, 30.3),
    ("Limpopo", -23.6, 29.4),
]

# Places whose name is printed on the map (the rest show as plain nodes
# so 70 labels don't crowd the country).
LABELLED = {
    "Cape Town", "Johannesburg", "Pretoria", "Durban", "Gqeberha",
    "Bloemfontein", "Kimberley", "Polokwane", "Mbombela", "Mahikeng",
    "Upington", "East London", "Pietermaritzburg", "George",
}
