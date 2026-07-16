"""Contract test: every payload in tests/fixtures/events/ must still parse against its
corresponding Pydantic model — catches drift the moment one side changes without the other
(docs/PLAN.md Phase 8)."""

import json
from pathlib import Path

import pytest

from src.modules.couriers.api.dtos import UpdateGpsRequest
from src.modules.deliveries.api.dtos import AcceptDeliveryRequest, UpdateDeliveryStageRequest
from src.modules.events.model.order_event import OrderCancelledEvent, OrderPreparingEvent, OrderStatusReadyEvent

_FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "events"

_MODEL_BY_FILENAME = {
    "order-preparing.json": OrderPreparingEvent,
    "order-cancelled.json": OrderCancelledEvent,
    "order-status-ready.json": OrderStatusReadyEvent,
    "accept-delivery.json": AcceptDeliveryRequest,
    "update-delivery-stage.json": UpdateDeliveryStageRequest,
    "update-courier-location.json": UpdateGpsRequest,
}


@pytest.mark.parametrize("filename,model", _MODEL_BY_FILENAME.items())
def test_fixture_parses_against_model(filename, model):
    payload = json.loads((_FIXTURES_DIR / filename).read_text())
    assert model.model_validate(payload) is not None
