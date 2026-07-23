from src.shared.db.supabase_client import get_connection
from src.shared.logger import logger


def get_profile(courier_id: str) -> dict:
    """Reads name/phone/vehicleType from `couriers` joined to `users`.

    Returns null fields (rather than fabricating data) if the DB isn't configured or the
    courier isn't found — see docs/PLAN.md Phase 2.
    """
    try:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                    SELECT c.vehicle_type, u.display_name, u.phone
                    FROM couriers c
                    JOIN users u ON u.id = c.user_id
                    WHERE c.id = %s
                    """,
                (courier_id,),
            )
            row = cur.fetchone()
        data = dict(zip(["vehicle_type", "display_name", "phone"], row, strict=True)) if row else None
    except Exception:
        logger.exception("Failed to fetch courier profile from DB | courier={}", courier_id)
        data = None

    if not data:
        return {"courier_id": courier_id, "name": None, "phone": None, "vehicle_type": None}

    return {
        "courier_id": courier_id,
        "name": data.get("display_name"),
        "phone": data.get("phone"),
        "vehicle_type": data.get("vehicle_type"),
    }
