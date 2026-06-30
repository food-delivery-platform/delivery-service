from dataclasses import dataclass
from datetime import datetime


@dataclass
class CourierLocation:
    courier_id: str
    lat: float
    lng: float
    updated_at: datetime
