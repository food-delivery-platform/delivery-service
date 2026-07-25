from src.shared.db.supabase_client import get_connection
from src.shared.logger import logger


def get_nearest_couriers(lat: float, lng: float, limit: int = 20) -> list[dict]:
    """Nearest couriers by PostGIS distance, via a `nearest_couriers(query_lat, query_lng,
    result_limit)` Postgres function over `courier_locations` (see docs/ARCHITECTURE.md §6
    for the underlying `<->` query this wraps).

    That function does not exist yet in database_rel's migrations as of this writing — a real,
    currently-open cross-repo gap, not a bug in this call. Returns [] on any failure (function
    missing, DB not configured, network error) rather than raising, so the Assignment Engine
    still creates the delivery_assignments row with an empty eligible list instead of crashing
    the event handler.

    Expected shape per row: {"courier_id": str, "lat": float, "lng": float}.
    """
    try:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM nearest_couriers(%s, %s, %s)",
                (lat, lng, limit),
            )
            rows = cur.fetchall()
            cols = [desc[0] for desc in cur.description]
            return [dict(zip(cols, row, strict=True)) for row in rows]
    except Exception:
        logger.exception("Failed to query nearest couriers from DB | lat={} lng={}", lat, lng)
        return []
