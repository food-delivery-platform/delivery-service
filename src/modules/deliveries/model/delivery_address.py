from dataclasses import dataclass
from typing import Optional


@dataclass
class DeliveryAddress:
    street: str
    city: str
    country: str
    lat: float
    lng: float
    apartment: Optional[str] = None
    notes: Optional[str] = None
