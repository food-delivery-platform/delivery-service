from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


class OrderEventType(str, Enum):
    ORDER_PREPARING = "order.preparing"
    ORDER_CANCELLED = "order.cancelled"
    ORDER_STATUS_READY = "order.status.ready"


@dataclass
class OrderEvent:
    event_type: OrderEventType
    order_id: str
    restaurant_id: str
    timestamp: datetime
    actor_id: Optional[str] = None
