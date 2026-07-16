from datetime import datetime

from pydantic import BaseModel

from src.modules.deliveries.model.delivery_address import DeliveryAddress
from src.modules.deliveries.model.delivery_stage import DeliveryStage


class DeliveryAssignment(BaseModel):
    """This service's own operational record for one order (table: delivery_assignments).

    Owned exclusively by delivery-service — see docs/ARCHITECTURE.md §0.7. Never written to
    Order Service's `active_orders`.
    """

    order_id: str
    restaurant_id: str
    restaurant_address: DeliveryAddress
    delivery_address: DeliveryAddress
    items: list[dict]  # snapshot from order.preparing, display-only
    currency: str
    total_amount: float
    eligible_courier_ids: list[str] = []
    assigned_courier_id: str | None = None
    # None until a courier accepts — the DeliveryStage enum only models post-acceptance stages.
    stage: DeliveryStage | None = None
    estimated_pickup_time: datetime | None = None
    estimated_delivery_time: datetime | None = None
    assigned_at: datetime | None = None
    picked_up_at: datetime | None = None
    delivered_at: datetime | None = None
    courier_confirmed: bool = False
    customer_confirmed: bool = False
    created_at: datetime
    updated_at: datetime
