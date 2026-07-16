import json
from pathlib import Path
from unittest.mock import patch

from src.modules.deliveries.repository import delivery_assignment_repository as repo
from src.modules.deliveries.service import assignment_engine
from src.modules.events.model.order_event import OrderPreparingEvent

_FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "events"


def _preparing_event() -> OrderPreparingEvent:
    payload = json.loads((_FIXTURES_DIR / "order-preparing.json").read_text())
    return OrderPreparingEvent.model_validate(payload)


def test_handle_order_preparing_creates_assignment(aws):
    with patch(
        "src.modules.deliveries.service.assignment_engine.get_nearest_couriers",
        return_value=[],
    ):
        assignment_engine.handle_order_preparing(_preparing_event())

    assignment = repo.get("order-xyz")
    assert assignment is not None
    assert assignment.restaurant_id == "rest-456"
    assert assignment.eligible_courier_ids == []


def test_handle_order_preparing_is_idempotent(aws):
    with patch(
        "src.modules.deliveries.service.assignment_engine.get_nearest_couriers",
        return_value=[],
    ) as mock_nearest:
        event = _preparing_event()
        assignment_engine.handle_order_preparing(event)
        assignment_engine.handle_order_preparing(event)
        # Second dispatch must be a no-op — SQS Standard gives no exactly-once guarantee.
        mock_nearest.assert_called_once()


def test_find_eligible_couriers_filters_by_distance_when_waze_unavailable():
    candidates = [
        {"courier_id": "near", "lat": 32.086, "lng": 34.782},  # ~150m from restaurant
        {"courier_id": "far", "lat": 33.5, "lng": 35.5},  # very far away
    ]
    with (
        patch(
            "src.modules.deliveries.service.assignment_engine.get_nearest_couriers",
            return_value=candidates,
        ),
        patch(
            "src.modules.deliveries.service.assignment_engine.get_travel_time_minutes",
            return_value=None,
        ),
    ):
        eligible = assignment_engine._find_eligible_couriers(32.0853, 34.7818)

    assert eligible == ["near"]


def test_handle_order_cancelled_releases_and_frees_courier(aws):
    with patch(
        "src.modules.deliveries.service.assignment_engine.get_nearest_couriers",
        return_value=[{"courier_id": "courier-1", "lat": 32.086, "lng": 34.782}],
    ):
        assignment_engine.handle_order_preparing(_preparing_event())
    repo.set_eligible_couriers("order-xyz", ["courier-1"])
    repo.accept("order-xyz", "courier-1", _preparing_event().timestamp)

    from src.modules.couriers.model.courier_state import CourierStatus
    from src.modules.couriers.repository import courier_state_repository

    courier_state_repository.set_status("courier-1", CourierStatus.BUSY, current_order_id="order-xyz")

    from src.modules.events.model.order_event import OrderCancelledEvent

    cancel_payload = json.loads((_FIXTURES_DIR / "order-cancelled.json").read_text())
    assignment_engine.handle_order_cancelled(OrderCancelledEvent.model_validate(cancel_payload))

    assignment = repo.get("order-xyz")
    assert assignment.assigned_courier_id is None

    freed_courier = courier_state_repository.get("courier-1")
    assert freed_courier.status == CourierStatus.AVAILABLE
    assert freed_courier.current_order_id is None
