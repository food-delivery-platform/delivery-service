from datetime import UTC, datetime

from src.modules.couriers.model.courier_state import CourierStatus
from src.modules.couriers.repository.courier_location_repository import get_nearest_couriers
from src.modules.couriers.service import courier_service
from src.modules.deliveries.model.delivery_address import DeliveryAddress
from src.modules.deliveries.model.delivery_assignment import DeliveryAssignment
from src.modules.deliveries.repository import delivery_assignment_repository as repo
from src.modules.events.model.order_event import OrderCancelledEvent, OrderPreparingEvent, OrderStatusReadyEvent
from src.shared.config.env import MAX_COURIER_DISTANCE_MINUTES
from src.shared.logger import logger
from src.shared.utils.geo import estimate_minutes_from_distance_km, haversine_distance_km


def handle_order_preparing(event: OrderPreparingEvent) -> None:
    if repo.get(event.order_id) is not None:
        # Standard (non-FIFO) SQS gives no exactly-once guarantee — creation must be idempotent.
        logger.debug("order.preparing already processed | order={}", event.order_id)
        return

    now = datetime.now(UTC)
    assignment = DeliveryAssignment(
        order_id=event.order_id,
        restaurant_id=event.restaurant_id,
        restaurant_address=DeliveryAddress(**event.restaurant_address.model_dump()),
        delivery_address=DeliveryAddress(**event.delivery_address.model_dump()),
        items=[item.model_dump() for item in event.items],
        currency=event.currency,
        total_amount=event.total_amount,
        estimated_pickup_time=event.estimated_pickup_time,
        estimated_delivery_time=event.estimated_delivery_time,
        created_at=now,
        updated_at=now,
    )
    repo.create(assignment)

    eligible_ids = _find_eligible_couriers(event.restaurant_address.lat, event.restaurant_address.lng)
    repo.set_eligible_couriers(event.order_id, eligible_ids)
    logger.info("Assignment engine complete | order={} eligible_count={}", event.order_id, len(eligible_ids))


def _find_eligible_couriers(restaurant_lat: float, restaurant_lng: float) -> list[str]:
    """PostGIS nearest-20, then distance-only filtering — the Waze-based version (Phase 5)
    calls Waze per candidate instead of this haversine estimate, falling back to it on failure."""
    candidates = get_nearest_couriers(restaurant_lat, restaurant_lng, limit=20)
    eligible_ids = []
    for candidate in candidates:
        distance_km = haversine_distance_km(restaurant_lat, restaurant_lng, candidate["lat"], candidate["lng"])
        minutes = estimate_minutes_from_distance_km(distance_km)
        if minutes <= MAX_COURIER_DISTANCE_MINUTES:
            eligible_ids.append(candidate["courier_id"])
    return eligible_ids


def handle_order_cancelled(event: OrderCancelledEvent) -> None:
    assignment = repo.get(event.order_id)
    if assignment is None:
        logger.warning("order.cancelled for unknown assignment | order={}", event.order_id)
        return
    previously_assigned = assignment.assigned_courier_id
    repo.release(event.order_id)
    if previously_assigned:
        courier_service.set_status(previously_assigned, CourierStatus.AVAILABLE, current_order_id=None)


def handle_order_status_ready(event: OrderStatusReadyEvent) -> None:
    repo.touch(event.order_id)
