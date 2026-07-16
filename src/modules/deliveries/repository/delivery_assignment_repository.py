from datetime import UTC, datetime

from src.modules.deliveries.model.delivery_assignment import DeliveryAssignment
from src.modules.deliveries.model.delivery_stage import DeliveryStage
from src.shared.aws.dynamodb_client import get_table
from src.shared.config.env import DYNAMODB_TABLE_DELIVERY_ASSIGNMENTS
from src.shared.errors.app_error import ConflictError
from src.shared.logger import logger
from src.shared.utils.dynamodb_types import floats_to_decimal


def _table():
    return get_table(DYNAMODB_TABLE_DELIVERY_ASSIGNMENTS)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _to_item(assignment: DeliveryAssignment) -> dict:
    # exclude_none so unset optionals are truly absent — required for accept()'s
    # attribute_not_exists(assigned_courier_id) conditional write to work on first accept.
    data = assignment.model_dump(mode="json", exclude_none=True)
    return floats_to_decimal(data)


def _from_item(item: dict) -> DeliveryAssignment:
    return DeliveryAssignment.model_validate(item)


def create(assignment: DeliveryAssignment) -> None:
    logger.info("Creating delivery assignment | order={}", assignment.order_id)
    _table().put_item(Item=_to_item(assignment))


def get(order_id: str) -> DeliveryAssignment | None:
    response = _table().get_item(Key={"order_id": order_id})
    item = response.get("Item")
    return _from_item(item) if item else None


def list_eligible_for_courier(courier_id: str) -> list[DeliveryAssignment]:
    """MVP: table scan + filter in Python — fine at this scale; no GSI defined for eligibility yet."""
    response = _table().scan()
    assignments = [_from_item(item) for item in response.get("Items", [])]
    return [a for a in assignments if a.assigned_courier_id is None and courier_id in a.eligible_courier_ids]


def set_eligible_couriers(order_id: str, courier_ids: list[str]) -> None:
    logger.info("Setting eligible couriers | order={} count={}", order_id, len(courier_ids))
    _table().update_item(
        Key={"order_id": order_id},
        UpdateExpression="SET eligible_courier_ids = :ids, updated_at = :ts",
        ExpressionAttributeValues={":ids": courier_ids, ":ts": _now()},
    )


def accept(order_id: str, courier_id: str, accepted_at: datetime) -> DeliveryAssignment:
    """First-writer-wins conditional write — see docs/ARCHITECTURE.md §15.6."""
    try:
        response = _table().update_item(
            Key={"order_id": order_id},
            UpdateExpression=(
                "SET assigned_courier_id = :courier_id, stage = :stage, assigned_at = :assigned_at, updated_at = :ts"
            ),
            ConditionExpression="attribute_not_exists(assigned_courier_id)",
            ExpressionAttributeValues={
                ":courier_id": courier_id,
                ":stage": DeliveryStage.ASSIGNED.value,
                ":assigned_at": accepted_at.isoformat(),
                ":ts": _now(),
            },
            ReturnValues="ALL_NEW",
        )
    except _table().meta.client.exceptions.ConditionalCheckFailedException as exc:
        raise ConflictError(f"Another courier already accepted order {order_id}") from exc
    return _from_item(response["Attributes"])


def update_stage(order_id: str, new_stage: DeliveryStage, at: datetime) -> DeliveryAssignment:
    ts = at.isoformat()
    set_parts = ["stage = :stage", "updated_at = :updated_ts"]
    values = {":stage": new_stage.value, ":updated_ts": _now()}
    if new_stage == DeliveryStage.PICKED_UP:
        set_parts.append("picked_up_at = :picked_up_at")
        values[":picked_up_at"] = ts
    elif new_stage == DeliveryStage.DELIVERED:
        set_parts.append("delivered_at = :delivered_at")
        values[":delivered_at"] = ts
    response = _table().update_item(
        Key={"order_id": order_id},
        UpdateExpression="SET " + ", ".join(set_parts),
        ExpressionAttributeValues=values,
        ReturnValues="ALL_NEW",
    )
    return _from_item(response["Attributes"])


def set_courier_confirmed(order_id: str) -> DeliveryAssignment:
    response = _table().update_item(
        Key={"order_id": order_id},
        UpdateExpression="SET courier_confirmed = :true, updated_at = :ts",
        ExpressionAttributeValues={":true": True, ":ts": _now()},
        ReturnValues="ALL_NEW",
    )
    return _from_item(response["Attributes"])


def set_customer_confirmed(order_id: str) -> DeliveryAssignment:
    response = _table().update_item(
        Key={"order_id": order_id},
        UpdateExpression="SET customer_confirmed = :true, updated_at = :ts",
        ExpressionAttributeValues={":true": True, ":ts": _now()},
        ReturnValues="ALL_NEW",
    )
    return _from_item(response["Attributes"])


def release(order_id: str) -> DeliveryAssignment | None:
    """order.cancelled — release any eligible-but-unaccepted state. No-op if never created."""
    existing = get(order_id)
    if existing is None:
        logger.warning("order.cancelled for unknown assignment | order={}", order_id)
        return None
    response = _table().update_item(
        Key={"order_id": order_id},
        UpdateExpression="SET updated_at = :ts REMOVE assigned_courier_id, eligible_courier_ids",
        ExpressionAttributeValues={":ts": _now()},
        ReturnValues="ALL_NEW",
    )
    return _from_item(response["Attributes"])


def touch(order_id: str) -> DeliveryAssignment | None:
    """order.status.ready — informational only at this stage; bumps updated_at. No-op if unknown."""
    existing = get(order_id)
    if existing is None:
        logger.warning("order.status.ready for unknown assignment | order={}", order_id)
        return None
    response = _table().update_item(
        Key={"order_id": order_id},
        UpdateExpression="SET updated_at = :ts",
        ExpressionAttributeValues={":ts": _now()},
        ReturnValues="ALL_NEW",
    )
    return _from_item(response["Attributes"])
