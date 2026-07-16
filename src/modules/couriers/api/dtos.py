from datetime import datetime

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class UpdateGpsRequest(BaseModel):
    lat: float
    lng: float
    timestamp: datetime


class _Schema(BaseModel):
    """Base for response DTOs — serialises to camelCase JSON."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class CourierProfileResponse(_Schema):
    courier_id: str
    name: str | None = None
    phone: str | None = None
    vehicle_type: str | None = None
