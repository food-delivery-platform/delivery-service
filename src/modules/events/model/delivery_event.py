from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from src.modules.couriers.model.vehicle_type import VehicleType


class DeliveryCourierAssignedEvent(BaseModel):
    event_type: Literal["delivery.courier_assigned"] = "delivery.courier_assigned"
    event_id: str
    timestamp: datetime
    order_id: str
    courier_id: str
    courier_name: str
    courier_phone: str
    vehicle_type: VehicleType
    estimated_pickup_time: datetime
    estimated_delivery_time: datetime
    actor_id: str = "SYSTEM"


class DeliveryPickedUpEvent(BaseModel):
    event_type: Literal["delivery.status.picked_up"] = "delivery.status.picked_up"
    event_id: str
    timestamp: datetime
    order_id: str
    courier_id: str
    actor_id: str


class DeliveryDeliveredEvent(BaseModel):
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


class DeliveryFailedEvent(BaseModel):
    event_type: Literal["delivery.status.failed"] = "delivery.status.failed"
    event_id: str
    timestamp: datetime
    order_id: str
    courier_id: str
    failure_reason: str
    failure_note: str | None = None
    actor_id: str


class DeliveryCourierReassignedEvent(BaseModel):
    event_type: Literal["delivery.courier_reassigned"] = "delivery.courier_reassigned"
    event_id: str
    timestamp: datetime
    order_id: str
    previous_courier_id: str
    new_courier_id: str
    reason: str
    actor_id: str = "SYSTEM"
