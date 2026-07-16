from src.shared.db.supabase_client import get_client
from src.shared.logger import logger


def get_profile(courier_id: str) -> dict:
    """Reads name/phone/vehicleType from Supabase `couriers` joined to `users`.

    Returns null fields (rather than fabricating data) if Supabase isn't configured or the
    courier isn't found — see docs/PLAN.md Phase 2.
    """
    try:
        response = (
            get_client()
            .table("couriers")
            .select("vehicle_type, users(display_name, phone)")
            .eq("id", courier_id)
            .maybe_single()
            .execute()
        )
        data = response.data if response else None
    except Exception:
        logger.exception("Failed to fetch courier profile from Supabase | courier={}", courier_id)
        data = None

    if not data:
        return {"courier_id": courier_id, "name": None, "phone": None, "vehicle_type": None}

    users = data.get("users") or {}
    return {
        "courier_id": courier_id,
        "name": users.get("display_name"),
        "phone": users.get("phone"),
        "vehicle_type": data.get("vehicle_type"),
    }
