from datetime import UTC, datetime

from src.modules.couriers.model.courier_state import CourierStatus
from src.modules.couriers.repository import courier_state_repository as repo


def test_get_missing_courier_returns_none(aws):
    assert repo.get("does-not-exist") is None


def test_upsert_location_defaults_status_to_offline(aws):
    repo.upsert_location("courier-1", 1.0, 2.0, datetime.now(UTC))
    state = repo.get("courier-1")
    assert state is not None
    assert state.status == CourierStatus.OFFLINE
    assert state.last_location.lat == 1.0
    assert state.last_location.lng == 2.0


def test_upsert_location_never_clobbers_existing_status_or_order(aws):
    repo.upsert_location("courier-1", 1.0, 2.0, datetime.now(UTC))
    repo.set_status("courier-1", CourierStatus.BUSY, current_order_id="order-1")

    repo.upsert_location("courier-1", 5.0, 6.0, datetime.now(UTC))

    state = repo.get("courier-1")
    assert state.status == CourierStatus.BUSY
    assert state.current_order_id == "order-1"
    assert state.last_location.lat == 5.0


def test_set_status_with_order_id_sets_current_order(aws):
    repo.set_status("courier-1", CourierStatus.BUSY, current_order_id="order-1")
    state = repo.get("courier-1")
    assert state.status == CourierStatus.BUSY
    assert state.current_order_id == "order-1"


def test_set_status_none_clears_current_order(aws):
    repo.set_status("courier-1", CourierStatus.BUSY, current_order_id="order-1")
    repo.set_status("courier-1", CourierStatus.AVAILABLE, current_order_id=None)
    state = repo.get("courier-1")
    assert state.status == CourierStatus.AVAILABLE
    assert state.current_order_id is None
