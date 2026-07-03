from datetime import datetime
from enum import Enum

from pydantic import BaseModel

from src.modules.couriers.model.courier_location import CourierLocation
from src.modules.couriers.model.vehicle_type import VehicleType


class CourierStatus(str, Enum):
    OFFLINE = "offline"
    AVAILABLE = "available"
    BUSY = "busy"


class CourierState(BaseModel):
    courier_id: str
    status: CourierStatus
    vehicle_type: VehicleType
    last_location: CourierLocation | None = None
    current_order_id: str | None = None
    updated_at: datetime
