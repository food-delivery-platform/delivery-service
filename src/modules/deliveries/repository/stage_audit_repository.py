from datetime import UTC, datetime
from uuid import uuid4

from src.shared.aws.dynamodb_client import get_table
from src.shared.config.env import DYNAMODB_TABLE_ORDER_EVENTS
from src.shared.logger import logger


def _table():
    return get_table(DYNAMODB_TABLE_ORDER_EVENTS)


def record(
    order_id: str,
    event_type: str,
    stage: str,
    actor_id: str,
    actor_type: str,
    previous_stage: str | None = None,
    courier_id: str | None = None,
    metadata: dict | None = None,
) -> None:
    """Immutable audit row — table: order_events (PK order_id, SK event_time). Never read back
    by this service; write-only compliance/analytics trail per
    delivery-service-message-contracts.md §5."""
    item = {
        "order_id": order_id,
        "event_time": datetime.now(UTC).isoformat(),
        "event_type": event_type,
        "stage": stage,
        "actor_id": actor_id,
        "actor_type": actor_type,
        "event_id": f"evt_{uuid4().hex}",
    }
    if previous_stage is not None:
        item["previous_stage"] = previous_stage
    if courier_id is not None:
        item["courier_id"] = courier_id
    if metadata:
        item["metadata"] = metadata
    logger.debug("Recording order_events audit row | order={} event_type={}", order_id, event_type)
    _table().put_item(Item=item)
