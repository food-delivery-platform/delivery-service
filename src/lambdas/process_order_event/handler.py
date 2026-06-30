import json
import logging
from src.shared.aws.sqs_client import parse_sqs_records

logger = logging.getLogger(__name__)

EVENT_HANDLERS = {
    "order.preparing": "_handle_order_preparing",
    "order.cancelled": "_handle_order_cancelled",
    "order.status.ready": "_handle_order_status_ready",
}


def handler(event: dict, context) -> None:
    records = parse_sqs_records(event)
    for record in records:
        event_type = record.get("eventType")
        handler_name = EVENT_HANDLERS.get(event_type)
        if handler_name:
            globals()[handler_name](record)
        else:
            logger.warning("Unknown event type: %s", event_type)


def _handle_order_preparing(record: dict) -> None:
    order_id = record["orderId"]
    logger.info("Processing order.preparing for order %s", order_id)
    # TODO: run assignment engine — PostGIS nearest couriers + write eligible_courier_ids to DynamoDB


def _handle_order_cancelled(record: dict) -> None:
    order_id = record["orderId"]
    logger.info("Processing order.cancelled for order %s", order_id)
    # TODO: release assigned courier (clear currentOrderId, set status=available)


def _handle_order_status_ready(record: dict) -> None:
    order_id = record["orderId"]
    logger.info("Processing order.status.ready for order %s", order_id)
    # TODO: update active_orders status so courier poll reflects food is ready
