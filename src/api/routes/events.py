from fastapi import APIRouter

from src.modules.events.model.order_event import (
    OrderCancelledEvent,
    OrderPreparingEvent,
    OrderStatusReadyEvent,
)
from src.shared.logger import logger

router = APIRouter(tags=["events"])

OrderEvent = OrderPreparingEvent | OrderCancelledEvent | OrderStatusReadyEvent


@router.post("/events", status_code=204)
async def process_order_event(event: OrderEvent):
    """Internal endpoint: accepts an order event payload for processing.

    In production this is driven by the SQS consumer background task.
    Available here for local testing and integration calls.
    """
    logger.info("Order event received | type={} event_id={} order={}", event.event_type, event.event_id, event.order_id)

    if isinstance(event, OrderPreparingEvent):
        logger.info(
            "Assignment engine triggered | order={} restaurant={} items={}",
            event.order_id,
            event.restaurant_id,
            len(event.items),
        )
        # TODO: run assignment engine — PostGIS nearest couriers + write eligible_courier_ids to DynamoDB

    elif isinstance(event, OrderCancelledEvent):
        logger.warning(
            "Order cancelled — releasing courier | order={} reason={}",
            event.order_id,
            event.reason,
        )
        # TODO: release assigned courier (clear currentOrderId, set status=available)

    elif isinstance(event, OrderStatusReadyEvent):
        logger.info(
            "Order ready for pickup | order={} courier={}",
            event.order_id,
            event.courier_id,
        )
        # TODO: update active_orders so courier poll reflects food is ready

    else:
        logger.warning("Unknown event type received | type={} order={}", event.event_type, event.order_id)
