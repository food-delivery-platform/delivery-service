from dataclasses import dataclass
from datetime import datetime

from src.modules.couriers.model.courier_state import CourierStatus
from src.modules.couriers.model.vehicle_type import VehicleType


@dataclass
class UpdateCourierLocationRequestDTO:
    lat: float
    lng: float


@dataclass
class UpdateCourierLocationResponseDTO:
    courier_id: str
    lat: float
    lng: float
    updated_at: datetime


@dataclass
class CourierDTO:
    courier_id: str
    user_id: str
    vehicle_type: VehicleType
    status: CourierStatus
    lat: float
    lng: float
    updated_at: datetime
