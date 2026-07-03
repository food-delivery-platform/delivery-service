from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from src.modules.deliveries.model.delivery_stage import DeliveryStage, FailureReason


class _Schema(BaseModel):
    """Base for all API DTOs — serialises to camelCase JSON."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


# ── ETA ──────────────────────────────────────────────────────────────────────


class EtaResponse(_Schema):
    estimated_delivery_minutes: int
    restaurant_to_customer_km: float
    calculated_at: datetime
    source: str = "waze"


# ── Available deliveries ─────────────────────────────────────────────────────


class AvailableOrderItem(_Schema):
    name: str
    quantity: int


class AvailableOrder(_Schema):
    order_id: str
    restaurant_id: str
    restaurant_name: str | None = None
    restaurant_address: dict[str, Any]
    customer_address: dict[str, Any]
    estimated_pickup_minutes: int | None = None
    estimated_delivery_minutes: int | None = None
    estimated_earnings: float | None = None
    currency: str
    items: list[AvailableOrderItem]


class AvailableDeliveriesResponse(_Schema):
    available_orders: list[AvailableOrder]


# ── Accept delivery ───────────────────────────────────────────────────────────


class AcceptDeliveryRequest(_Schema):
    courier_id: str
    accepted_at: datetime


class AcceptDeliveryResponse(_Schema):
    order_id: str
    status: str
    restaurant_address: dict[str, Any] | None = None


# ── Delivery stage update ────────────────────────────────────────────────────


class UpdateDeliveryStageRequest(_Schema):
    courier_id: str
    new_stage: DeliveryStage
    failure_reason: FailureReason | None = None


class UpdateDeliveryStageResponse(_Schema):
    order_id: str
    stage: DeliveryStage
    updated_at: datetime


# ── Confirm delivery (customer) ───────────────────────────────────────────────


class ConfirmDeliveryRequest(_Schema):
    customer_id: str


# ── Delivery state ────────────────────────────────────────────────────────────


class CourierLastLocation(_Schema):
    lat: float
    lng: float
    updated_at: datetime


class DeliveryStateResponse(_Schema):
    order_id: str
    status: str
    courier_id: str | None = None
    courier_name: str | None = None
    courier_phone: str | None = None
    courier_last_location: CourierLastLocation | None = None
    estimated_delivery_time: datetime | None = None
    assigned_at: datetime | None = None
    picked_up_at: datetime | None = None
    delivered_at: datetime | None = None
