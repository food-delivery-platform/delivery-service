import math

_EARTH_RADIUS_KM = 6371.0
# Rough MVP assumption for a bike/car mix in a dense urban area — no per-courier vehicle
# speed model exists anywhere in the docs, so this is the single tunable constant for the
# distance-only ETA fallback (Waze failure, or Waze not called at all yet).
_ASSUMED_AVG_SPEED_KMH = 25.0


def haversine_distance_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * _EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def estimate_minutes_from_distance_km(distance_km: float) -> float:
    return (distance_km / _ASSUMED_AVG_SPEED_KMH) * 60
