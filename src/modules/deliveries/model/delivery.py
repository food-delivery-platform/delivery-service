from datetime import datetime

from pydantic import BaseModel

from src.modules.deliveries.model.delivery_address import DeliveryAddress
from src.modules.deliveries.model.delivery_stage import DeliveryStage


class Delivery(BaseModel):
    order_id: str
    stage: DeliveryStage
    courier_id: str | None = None
    courier_name: str | None = None
    courier_phone: str | None = None
    restaurant_address: DeliveryAddress | None = None
    delivery_address: DeliveryAddress | None = None
    estimated_pickup_time: datetime | None = None
    estimated_delivery_time: datetime | None = None
    assigned_at: datetime | None = None
    picked_up_at: datetime | None = None
    delivered_at: datetime | None = None
