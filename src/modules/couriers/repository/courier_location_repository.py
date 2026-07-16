from src.shared.db.supabase_client import get_client
from src.shared.logger import logger


def get_nearest_couriers(lat: float, lng: float, limit: int = 20) -> list[dict]:
    """Nearest couriers by PostGIS distance, via a `nearest_couriers(query_lat, query_lng,
    result_limit)` Postgres RPC over Supabase `courier_locations` (see docs/ARCHITECTURE.md §6
    for the underlying `<->` query this wraps).

    That RPC does not exist yet in database_rel's migrations as of this writing — a real,
    currently-open cross-repo gap, not a bug in this call. Returns [] on any failure (RPC
    missing, Supabase not configured, network error) rather than raising, so the Assignment
    Engine still creates the delivery_assignments row with an empty eligible list instead of
    crashing the event handler.

    Expected shape per row: {"courier_id": str, "lat": float, "lng": float}.
    """
    try:
        response = (
            get_client()
            .rpc(
                "nearest_couriers",
                {"query_lat": lat, "query_lng": lng, "result_limit": limit},
            )
            .execute()
        )
        return response.data or []
    except Exception:
        logger.exception("Failed to query nearest couriers from Supabase | lat={} lng={}", lat, lng)
        return []
