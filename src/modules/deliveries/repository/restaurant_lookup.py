from src.shared.db.supabase_client import get_client
from src.shared.logger import logger


def get_restaurant_name(restaurant_id: str) -> str | None:
    """Best-effort Supabase `venues` lookup. Returns None (not a fabricated name) on any failure —
    the inbound order.preparing event carries no restaurant name, only restaurantId."""
    try:
        response = get_client().table("venues").select("name").eq("id", restaurant_id).maybe_single().execute()
        data = response.data if response else None
    except Exception:
        logger.exception("Failed to fetch restaurant name from Supabase | restaurant={}", restaurant_id)
        data = None
    return data.get("name") if data else None


def get_restaurant_location(restaurant_id: str) -> tuple[float, float] | None:
    """Best-effort Supabase venues+addresses lookup for GET /deliveries/eta — the endpoint
    receives restaurantId (not coordinates), so this is the only source of the restaurant's
    own lat/lng."""
    try:
        response = (
            get_client()
            .table("venues")
            .select("addresses(latitude, longitude)")
            .eq("id", restaurant_id)
            .maybe_single()
            .execute()
        )
        data = response.data if response else None
    except Exception:
        logger.exception("Failed to fetch restaurant location from Supabase | restaurant={}", restaurant_id)
        data = None

    if not data:
        return None
    address = data.get("addresses") or {}
    lat, lng = address.get("latitude"), address.get("longitude")
    if lat is None or lng is None:
        return None
    return float(lat), float(lng)
