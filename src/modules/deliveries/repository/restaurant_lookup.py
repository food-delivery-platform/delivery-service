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
