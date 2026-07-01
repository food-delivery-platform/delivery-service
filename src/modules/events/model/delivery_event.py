from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


class DeliveryEventType(str, Enum):
    COURIER_ASSIGNED = "delivery.courier_assigned"
    STATUS_PICKED_UP = "delivery.status.picked_up"
    STATUS_DELIVERED = "delivery.status.delivered"
    STATUS_FAILED = "delivery.status.failed"
    COURIER_REASSIGNED = "delivery.courier_reassigned"


@dataclass
class DeliveryEvent:
    event_type: DeliveryEventType
    delivery_id: str
    order_id: str
    timestamp: datetime
    courier_id: Optional[str] = None
    actor_id: Optional[str] = None
