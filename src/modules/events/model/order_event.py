from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class Address(BaseModel):
    lat: float
    lng: float
    street: str | None = None
    city: str | None = None
    address_id: str | None = None


class OrderItem(BaseModel):
    menu_item_id: str = Field(alias="menuItemId")
    name: str
    quantity: int
    time_to_prepare: int | None = Field(default=None, alias="timeToPrepare")

    model_config = {"populate_by_name": True}


class OrderPreparingEvent(BaseModel):
    event_type: Literal["order.preparing"] = Field(alias="eventType")
    event_id: str = Field(alias="eventId")
    timestamp: datetime
    order_id: str = Field(alias="orderId")
    customer_id: str = Field(alias="customerId")
    restaurant_id: str = Field(alias="restaurantId")
    restaurant_address: Address = Field(alias="restaurantAddress")
    delivery_address: Address = Field(alias="deliveryAddress")
    estimated_pickup_time: datetime = Field(alias="estimatedPickupTime")
    estimated_delivery_time: datetime = Field(alias="estimatedDeliveryTime")
    items: list[OrderItem]
    total_amount: float = Field(alias="totalAmount")
    currency: str
    actor_id: str = Field(alias="actorId")

    model_config = {"populate_by_name": True}


class OrderCancelledEvent(BaseModel):
    event_type: Literal["order.cancelled"] = Field(alias="eventType")
    event_id: str = Field(alias="eventId")
    timestamp: datetime
    order_id: str = Field(alias="orderId")
    reason: str
    actor_id: str = Field(alias="actorId")

    model_config = {"populate_by_name": True}


class OrderStatusReadyEvent(BaseModel):
    event_type: Literal["order.status.ready"] = Field(alias="eventType")
    event_id: str = Field(alias="eventId")
    timestamp: datetime
    order_id: str = Field(alias="orderId")
    restaurant_id: str = Field(alias="restaurantId")
    courier_id: str = Field(alias="courierId")
    actor_id: str = Field(alias="actorId")

    model_config = {"populate_by_name": True}
