from pydantic import BaseModel


class DeliveryAddress(BaseModel):
    lat: float
    lng: float
    street: str | None = None
    city: str | None = None
    address_id: str | None = None
