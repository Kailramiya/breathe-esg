"""
DEFRA 2023 Greenhouse Gas Reporting Conversion Factors.
Source: https://www.gov.uk/government/publications/greenhouse-gas-reporting-conversion-factors-2023

Factors are snapshotted here (not in the database) so they are version-controlled
and transparent. When a record is created, the factor value AND source string are
stored on NormalizedRecord so that updating this file never retroactively changes
approved or locked records.
"""

import math

# ---------------------------------------------------------------------------
# Scope 1 — Fuel combustion (kgCO2e per unit)
# ---------------------------------------------------------------------------
FUEL_FACTORS = {
    # key: (factor_kgco2e_per_unit, canonical_unit, aliases)
    "diesel": {
        "factor": 2.51839,
        "unit": "L",
        "aliases": ["diesel", "diesel kraftstoff", "hsd", "gasoil", "gas oil"],
    },
    "petrol": {
        "factor": 2.16846,
        "unit": "L",
        "aliases": ["petrol", "ottokraftstoff", "gasoline", "unleaded"],
    },
    "natural_gas": {
        "factor": 2.02428,
        "unit": "M3",
        "aliases": ["natural gas", "erdgas", "ngas", "natural_gas", "lng", "cng"],
    },
    "lpg": {
        "factor": 1.55540,
        "unit": "KG",
        "aliases": ["lpg", "flussiggas", "flüssiggas", "liquefied petroleum"],
    },
}

FACTOR_SOURCE = "DEFRA_2023"

# ---------------------------------------------------------------------------
# Scope 2 — Purchased electricity (kgCO2e per kWh)
# UK 2023 grid emission factor (location-based)
# ---------------------------------------------------------------------------
ELECTRICITY_FACTOR_KWH = 0.20493
ELECTRICITY_FACTOR_SOURCE = "DEFRA_2023_UK_GRID"

# ---------------------------------------------------------------------------
# Scope 3 — Business travel (kgCO2e per passenger-km or per room-night)
# Includes Radiative Forcing Index (RFI) of 1.891 for flights per DEFRA 2023.
# ---------------------------------------------------------------------------

# Flights — by haul and class
FLIGHT_FACTORS = {
    # short-haul = < 3700 km
    ("short", "economy"):  0.25397,
    ("short", "business"): 0.38096,
    ("short", "first"):    0.56694,
    ("short", "unknown"):  0.25397,   # default to economy if class missing

    # long-haul = >= 3700 km
    ("long", "economy"):   0.15302,
    ("long", "business"):  0.42849,
    ("long", "first"):     0.54387,
    ("long", "unknown"):   0.15302,
}

FLIGHT_SHORT_HAUL_THRESHOLD_KM = 3700

# Hotel — UK average per room-night
HOTEL_FACTOR_ROOM_NIGHT = 31.0
HOTEL_FACTOR_SOURCE = "DEFRA_2023"

# Ground transport
TAXI_FACTOR_KM = 0.14869          # taxi/rideshare per passenger-km
CAR_RENTAL_FACTOR_KM = 0.19327    # average car per km

TRAVEL_FACTOR_SOURCE = "DEFRA_2023"

# ---------------------------------------------------------------------------
# Airport lat/lon lookup (IATA codes → decimal degrees)
# Limited to the most common routes in corporate travel. A production system
# would use an aviation DB (e.g. OurAirports, OpenFlights).
# ---------------------------------------------------------------------------
AIRPORT_COORDS = {
    "LHR": (51.4775, -0.4614),    # London Heathrow
    "LGW": (51.1481, -0.1903),    # London Gatwick
    "MAN": (53.3537, -2.2750),    # Manchester
    "BHX": (52.4539, -1.7480),    # Birmingham
    "EDI": (55.9500, -3.3725),    # Edinburgh
    "CDG": (49.0097,  2.5479),    # Paris Charles de Gaulle
    "AMS": (52.3086,  4.7639),    # Amsterdam Schiphol
    "FRA": (50.0379,  8.5622),    # Frankfurt
    "JFK": (40.6413, -73.7781),   # New York JFK
    "EWR": (40.6895, -74.1745),   # New York Newark
    "ORD": (41.9742, -87.9073),   # Chicago O'Hare
    "LAX": (33.9425, -118.4081),  # Los Angeles
    "SFO": (37.6213, -122.3790),  # San Francisco
    "DXB": (25.2532,  55.3657),   # Dubai
    "SIN": (1.3644,   103.9915),  # Singapore Changi
    "HKG": (22.3080,  113.9185),  # Hong Kong
    "BOM": (19.0896,  72.8656),   # Mumbai
    "DEL": (28.5562,  77.1000),   # Delhi
    "NRT": (35.7647,  140.3864),  # Tokyo Narita
    "SYD": (-33.9399, 151.1753),  # Sydney
    "GRU": (-23.4356, -46.4731),  # São Paulo
    "DUS": (51.2895,   6.7668),   # Düsseldorf
    "BCN": (41.2971,   2.0785),   # Barcelona
    "MAD": (40.4936,  -3.5668),   # Madrid
    "FCO": (41.8003,  12.2389),   # Rome Fiumicino
    "BRU": (50.9010,   4.4844),   # Brussels
    "ZRH": (47.4647,   8.5492),   # Zurich
    "CPH": (55.6180,  12.6508),   # Copenhagen
    "ARN": (59.6519,  17.9186),   # Stockholm Arlanda
    "OSL": (60.1939,  11.1004),   # Oslo Gardermoen
    "HEL": (60.3183,  24.9630),   # Helsinki
    "IST": (41.2608,  28.7418),   # Istanbul
    "CAI": (30.1219,  31.4056),   # Cairo
    "JNB": (-26.1367, 28.2411),   # Johannesburg
    "NBO": (-1.3192,  36.9275),   # Nairobi
    "IAD": (38.9531, -77.4565),   # Washington Dulles
    "YYZ": (43.6772, -79.6306),   # Toronto Pearson
    "MEX": (19.4363, -99.0721),   # Mexico City
    "BOG": (4.7016,  -74.1469),   # Bogotá
    "LIM": (-12.0219, -77.1143),  # Lima
}


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two points in kilometres."""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def flight_distance_km(origin_iata: str, dest_iata: str) -> float | None:
    """Return great-circle distance for a flight, or None if codes not in lookup."""
    o = AIRPORT_COORDS.get(origin_iata.upper())
    d = AIRPORT_COORDS.get(dest_iata.upper())
    if o is None or d is None:
        return None
    return haversine_km(o[0], o[1], d[0], d[1])


def flight_co2e(distance_km: float, booking_class: str) -> tuple[float, float]:
    """
    Returns (kgCO2e, factor_used).
    booking_class should be one of: economy, business, first, unknown.
    """
    haul = "short" if distance_km < FLIGHT_SHORT_HAUL_THRESHOLD_KM else "long"
    cls = booking_class.lower() if booking_class else "unknown"
    if cls not in ("economy", "business", "first"):
        cls = "unknown"
    factor = FLIGHT_FACTORS[(haul, cls)]
    return distance_km * factor, factor


def resolve_fuel_factor(material_desc: str, unit: str) -> dict | None:
    """
    Match a SAP material description to a fuel type and return its emission factor.
    Returns None if no match found.
    """
    desc_lower = material_desc.lower().strip()
    for fuel_key, info in FUEL_FACTORS.items():
        if any(alias in desc_lower for alias in info["aliases"]):
            return {
                "fuel_key": fuel_key,
                "factor": info["factor"],
                "canonical_unit": info["unit"],
                "source": FACTOR_SOURCE,
            }
    return None


def normalize_unit_to_canonical(quantity: float, unit: str, canonical_unit: str) -> float | None:
    """
    Convert between compatible units for the same fuel type.
    Returns None if conversion is not supported (flags as warning).
    """
    unit = unit.upper().strip()
    canonical_unit = canonical_unit.upper().strip()

    if unit == canonical_unit:
        return quantity

    conversions = {
        # volume
        ("ML", "L"):  quantity / 1000,
        ("M3", "L"):  quantity * 1000,
        ("GAL", "L"): quantity * 3.78541,    # US gallon
        # mass
        ("G", "KG"):  quantity / 1000,
        ("T", "KG"):  quantity * 1000,
        ("LB", "KG"): quantity * 0.453592,
        # energy
        ("MWH", "KWH"): quantity * 1000,
        ("GJ", "KWH"):  quantity * 277.778,
    }
    return conversions.get((unit, canonical_unit))
