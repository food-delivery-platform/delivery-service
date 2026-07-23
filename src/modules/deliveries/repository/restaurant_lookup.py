from src.shared.db.supabase_client import get_connection
from src.shared.logger import logger


def get_restaurant_name(restaurant_id: str) -> str | None:
    """Best-effort `venues` lookup. Returns None (not a fabricated name) on any failure —
    the inbound order.preparing event carries no restaurant name, only restaurantId."""
    try:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT name FROM venues WHERE id = %s", (restaurant_id,))
            row = cur.fetchone()
        return row[0] if row else None
    except Exception:
        logger.exception("Failed to fetch restaurant name from DB | restaurant={}", restaurant_id)
        return None


def get_restaurant_location(restaurant_id: str) -> tuple[float, float] | None:
    """Best-effort venues+addresses lookup for GET /deliveries/eta — the endpoint
    receives restaurantId (not coordinates), so this is the only source of the restaurant's
    own lat/lng."""
    try:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                    SELECT a.latitude, a.longitude
                    FROM venues v
                    JOIN addresses a ON a.venue_id = v.id
                    WHERE v.id = %s
                    """,
                (restaurant_id,),
            )
            row = cur.fetchone()
    except Exception:
        logger.exception("Failed to fetch restaurant location from DB | restaurant={}", restaurant_id)
        return None

    if not row:
        return None
    lat, lng = row[0], row[1]
    if lat is None or lng is None:
        return None
    return float(lat), float(lng)
