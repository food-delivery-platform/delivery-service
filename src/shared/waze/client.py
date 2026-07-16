import requests

from src.shared.config.env import WAZE_API_KEY
from src.shared.logger import logger

_ROUTING_URL = "https://waze.com/row-RoutingManager/routingRequest"
_TIMEOUT_SECONDS = 5


def get_travel_time_minutes(from_lat: float, from_lng: float, to_lat: float, to_lng: float) -> float | None:
    """Returns Waze travel time in minutes, or None on any failure/timeout/missing API key —
    callers fall back to haversine-distance estimation (shared/utils/geo.py) per
    docs/ARCHITECTURE.md §15.6."""
    if not WAZE_API_KEY:
        return None
    try:
        response = requests.get(
            _ROUTING_URL,
            params={
                "from": f"ll.{from_lat},{from_lng}",
                "to": f"ll.{to_lat},{to_lng}",
                "at": 0,
                "returnJSON": "true",
            },
            headers={"Authorization": WAZE_API_KEY},
            timeout=_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        total_route_time_seconds = response.json()["alternatives"][0]["response"]["totalRouteTime"]
        return total_route_time_seconds / 60
    except Exception:
        logger.warning("Waze API call failed — falling back to distance-only estimate")
        return None
