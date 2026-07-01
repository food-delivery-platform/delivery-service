from datetime import datetime

from pydantic import BaseModel


class CourierLocation(BaseModel):
    lat: float
    lng: float
    updated_at: datetime
