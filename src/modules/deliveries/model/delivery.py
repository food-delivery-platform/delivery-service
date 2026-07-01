from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from .delivery_address import DeliveryAddress
from .delivery_stage import DeliveryStage


@dataclass
class Delivery:
    delivery_id: str
    order_id: str
    customer_id: str
    restaurant_id: str
    delivery_address: DeliveryAddress
    stage: DeliveryStage
    created_at: datetime
    updated_at: datetime
    courier_id: Optional[str] = None
    estimated_delivery_minutes: Optional[int] = None
    picked_up_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
