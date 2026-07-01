from datetime import datetime

from pydantic import BaseModel


class UpdateGpsRequest(BaseModel):
    lat: float
    lng: float
    timestamp: datetime
