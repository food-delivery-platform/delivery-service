"""Unit tests for delivery_assignment_repository — the first-writer-wins conditional write is
the correctness-critical path (docs/PLAN.md Phase 8)."""

from datetime import UTC, datetime

import pytest

from src.modules.deliveries.model.delivery_address import DeliveryAddress
from src.modules.deliveries.model.delivery_assignment import DeliveryAssignment
from src.modules.deliveries.model.delivery_stage import DeliveryStage
from src.modules.deliveries.repository import delivery_assignment_repository as repo
from src.shared.errors.app_error import ConflictError


def _make_assignment(order_id: str = "order-1") -> DeliveryAssignment:
    now = datetime.now(UTC)
    return DeliveryAssignment(
        order_id=order_id,
        restaurant_id="rest-1",
        restaurant_address=DeliveryAddress(lat=1.0, lng=2.0),
        delivery_address=DeliveryAddress(lat=3.0, lng=4.0),
        items=[{"name": "Pizza", "quantity": 1}],
        currency="ILS",
        total_amount=50.0,
        created_at=now,
        updated_at=now,
    )


def test_create_and_get_roundtrip(aws):
    repo.create(_make_assignment())
    fetched = repo.get("order-1")
    assert fetched is not None
    assert fetched.restaurant_id == "rest-1"
    assert fetched.stage is None  # unset until a courier accepts


def test_get_missing_returns_none(aws):
    assert repo.get("does-not-exist") is None


def test_accept_first_writer_wins(aws):
    repo.create(_make_assignment())
    accepted = repo.accept("order-1", "courier-1", datetime.now(UTC))
    assert accepted.assigned_courier_id == "courier-1"
    assert accepted.stage == DeliveryStage.ASSIGNED


def test_accept_conflict_raises_for_second_courier(aws):
    repo.create(_make_assignment())
    now = datetime.now(UTC)
    repo.accept("order-1", "courier-1", now)
    with pytest.raises(ConflictError):
        repo.accept("order-1", "courier-2", now)


def test_set_eligible_couriers_and_list(aws):
    repo.create(_make_assignment())
    repo.set_eligible_couriers("order-1", ["courier-1", "courier-2"])
    eligible = repo.list_eligible_for_courier("courier-1")
    assert [a.order_id for a in eligible] == ["order-1"]
    assert repo.list_eligible_for_courier("courier-3") == []


def test_list_eligible_excludes_already_assigned(aws):
    repo.create(_make_assignment())
    repo.set_eligible_couriers("order-1", ["courier-1"])
    repo.accept("order-1", "courier-1", datetime.now(UTC))
    assert repo.list_eligible_for_courier("courier-1") == []


def test_update_stage_sets_stage_specific_timestamps(aws):
    repo.create(_make_assignment())
    now = datetime.now(UTC)
    picked = repo.update_stage("order-1", DeliveryStage.PICKED_UP, now)
    assert picked.stage == DeliveryStage.PICKED_UP
    assert picked.picked_up_at is not None
    assert picked.delivered_at is None

    delivered = repo.update_stage("order-1", DeliveryStage.DELIVERED, now)
    assert delivered.delivered_at is not None


def test_confirmation_flags_are_independent(aws):
    repo.create(_make_assignment())
    after_courier = repo.set_courier_confirmed("order-1")
    assert after_courier.courier_confirmed is True
    assert after_courier.customer_confirmed is False

    after_customer = repo.set_customer_confirmed("order-1")
    assert after_customer.courier_confirmed is True
    assert after_customer.customer_confirmed is True


def test_release_clears_assignment_and_eligibility(aws):
    repo.create(_make_assignment())
    repo.set_eligible_couriers("order-1", ["courier-1"])
    repo.accept("order-1", "courier-1", datetime.now(UTC))
    released = repo.release("order-1")
    assert released.assigned_courier_id is None
    assert released.eligible_courier_ids == []


def test_release_unknown_order_is_a_noop(aws):
    assert repo.release("does-not-exist") is None


def test_touch_unknown_order_is_a_noop(aws):
    assert repo.touch("does-not-exist") is None
