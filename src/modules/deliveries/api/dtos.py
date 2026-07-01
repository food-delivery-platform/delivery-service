from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from src.modules.deliveries.model.delivery_stage import DeliveryStage


@dataclass
class DeliveryAddressDTO:
    street: str
    city: str
    country: str
    lat: float
    lng: float
    apartment: Optional[str] = None
    notes: Optional[str] = None


@dataclass
class DeliveryDTO:
    delivery_id: str
    order_id: str
    customer_id: str
    restaurant_id: str
    delivery_address: DeliveryAddressDTO
    stage: DeliveryStage
    created_at: datetime
    updated_at: datetime
    courier_id: Optional[str] = None
    estimated_delivery_minutes: Optional[int] = None
    picked_up_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None


@dataclass
class AvailableDeliveryDTO:
    order_id: str
    restaurant_id: str
    delivery_address: DeliveryAddressDTO
    estimated_delivery_minutes: Optional[int]


@dataclass
class GetAvailableDeliveriesResponseDTO:
    deliveries: List[AvailableDeliveryDTO]


@dataclass
class AcceptDeliveryResponseDTO:
    delivery_id: str
    order_id: str
    courier_id: str
    stage: DeliveryStage


@dataclass
class UpdateDeliveryStageRequestDTO:
    stage: DeliveryStage


@dataclass
class UpdateDeliveryStageResponseDTO:
    delivery_id: str
    order_id: str
    stage: DeliveryStage
    updated_at: datetime


@dataclass
class ConfirmDeliveryResponseDTO:
    delivery_id: str
    order_id: str
    stage: DeliveryStage
    delivered_at: datetime


@dataclass
class GetEtaRequestDTO:
    restaurant_id: str
    delivery_lat: float
    delivery_lng: float


@dataclass
class GetEtaResponseDTO:
    estimated_delivery_minutes: int
