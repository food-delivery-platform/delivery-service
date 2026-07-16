from datetime import datetime

from src.modules.couriers.model.courier_state import CourierState, CourierStatus
from src.modules.couriers.repository import courier_profile_repository, courier_state_repository


def update_gps(courier_id: str, lat: float, lng: float, timestamp: datetime) -> None:
    courier_state_repository.upsert_location(courier_id, lat, lng, timestamp)


def get_state(courier_id: str) -> CourierState | None:
    return courier_state_repository.get(courier_id)


def set_status(courier_id: str, status: CourierStatus, current_order_id: str | None = None) -> None:
    courier_state_repository.set_status(courier_id, status, current_order_id)


def get_profile(courier_id: str) -> dict:
    return courier_profile_repository.get_profile(courier_id)
