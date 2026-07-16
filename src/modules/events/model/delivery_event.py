from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from src.modules.couriers.model.vehicle_type import VehicleType


class _Schema(BaseModel):
    """Base for outbound SNS event DTOs — serialises to camelCase JSON, matching
    delivery-service-message-contracts.md."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class DeliveryCourierAssignedEvent(_Schema):
    event_type: Literal["delivery.courier_assigned"] = "delivery.courier_assigned"
    event_id: str
    timestamp: datetime
    order_id: str
    courier_id: str
    # Best-effort lookups (Supabase courier profile) — null rather than fabricated when unavailable.
    courier_name: str | None = None
    courier_phone: str | None = None
    vehicle_type: VehicleType | None = None
    estimated_pickup_time: datetime | None = None
    estimated_delivery_time: datetime | None = None
    actor_id: str = "SYSTEM"


class DeliveryPickedUpEvent(_Schema):
    event_type: Literal["delivery.status.picked_up"] = "delivery.status.picked_up"
    event_id: str
    timestamp: datetime
    order_id: str
    courier_id: str
    actor_id: str


class DeliveryDeliveredEvent(_Schema):
    event_type: Literal["delivery.status.delivered"] = "delivery.status.delivered"
    event_id: str
    timestamp: datetime
    order_id: str
    courier_id: str
    courier_confirmed: bool
    customer_confirmed: bool
    confirmed_by: Literal["COURIER", "CUSTOMER"]
    actual_delivery_time: datetime
    actor_id: str


class DeliveryFailedEvent(_Schema):
    event_type: Literal["delivery.status.failed"] = "delivery.status.failed"
    event_id: str
    timestamp: datetime
    order_id: str
    courier_id: str
    failure_reason: str
    failure_note: str | None = None
    actor_id: str


class DeliveryCourierReassignedEvent(_Schema):
    event_type: Literal["delivery.courier_reassigned"] = "delivery.courier_reassigned"
    event_id: str
    timestamp: datetime
    order_id: str
    previous_courier_id: str
    new_courier_id: str
    reason: str
    actor_id: str = "SYSTEM"
