from fastapi import APIRouter

from src.modules.events.service.event_dispatcher import OrderEvent, dispatch
from src.shared.logger import logger

router = APIRouter(tags=["events"])


@router.post("/events", status_code=204)
async def process_order_event(event: OrderEvent):
    """Internal endpoint: accepts an order event payload for processing.

    In production this is driven by the SQS consumer background task.
    Available here for local testing and integration calls.
    """
    logger.info("Order event received | type={} event_id={} order={}", event.event_type, event.event_id, event.order_id)
    dispatch(event)
