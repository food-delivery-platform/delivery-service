from datetime import UTC, datetime
from decimal import Decimal

from src.modules.couriers.model.courier_location import CourierLocation
from src.modules.couriers.model.courier_state import CourierState, CourierStatus
from src.modules.couriers.model.vehicle_type import VehicleType
from src.shared.aws.dynamodb_client import get_table
from src.shared.config.env import DYNAMODB_TABLE_COURIER_STATES
from src.shared.logger import logger


def _table():
    return get_table(DYNAMODB_TABLE_COURIER_STATES)


def _from_item(item: dict) -> CourierState:
    last_location = item.get("lastLocation")
    return CourierState(
        courier_id=item["courierId"],
        status=CourierStatus(item["status"]),
        vehicle_type=VehicleType(item["vehicleType"]) if item.get("vehicleType") else None,
        current_order_id=item.get("currentOrderId"),
        last_location=CourierLocation(
            lat=float(last_location["lat"]),
            lng=float(last_location["lng"]),
            updated_at=last_location["updatedAt"],
        )
        if last_location
        else None,
        updated_at=item["updatedAt"],
    )


def get(courier_id: str) -> CourierState | None:
    response = _table().get_item(Key={"courierId": courier_id})
    item = response.get("Item")
    if item is None:
        return None
    return _from_item(item)


def upsert_location(courier_id: str, lat: float, lng: float, timestamp: datetime) -> None:
    """UpdateItem only touches lastLocation/updatedAt — never clobbers status/currentOrderId.

    Defaults status to OFFLINE via if_not_exists so a courier's very first GPS ping (before any
    status transition has been recorded) still creates a well-formed item.
    """
    ts = timestamp.isoformat()
    logger.debug("Upserting courier location | courier={} lat={} lng={}", courier_id, lat, lng)
    _table().update_item(
        Key={"courierId": courier_id},
        UpdateExpression=(
            "SET lastLocation = :loc, updatedAt = :ts, #status = if_not_exists(#status, :default_status)"
        ),
        ExpressionAttributeNames={"#status": "status"},
        ExpressionAttributeValues={
            ":loc": {"lat": Decimal(str(lat)), "lng": Decimal(str(lng)), "updatedAt": ts},
            ":ts": ts,
            ":default_status": CourierStatus.OFFLINE.value,
        },
    )


def set_status(courier_id: str, status: CourierStatus, current_order_id: str | None = None) -> None:
    """Upserts status + updatedAt. `current_order_id=None` clears any existing assignment."""
    ts = datetime.now(UTC).isoformat()
    logger.info("Setting courier status | courier={} status={} order={}", courier_id, status, current_order_id)
    if current_order_id is not None:
        _table().update_item(
            Key={"courierId": courier_id},
            UpdateExpression="SET #status = :status, currentOrderId = :order_id, updatedAt = :ts",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={":status": status.value, ":order_id": current_order_id, ":ts": ts},
        )
    else:
        _table().update_item(
            Key={"courierId": courier_id},
            UpdateExpression="SET #status = :status, updatedAt = :ts REMOVE currentOrderId",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={":status": status.value, ":ts": ts},
        )
