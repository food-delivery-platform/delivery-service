from src.modules.deliveries.service import assignment_engine
from src.modules.events.model.order_event import OrderCancelledEvent, OrderPreparingEvent, OrderStatusReadyEvent
from src.shared.logger import logger

OrderEvent = OrderPreparingEvent | OrderCancelledEvent | OrderStatusReadyEvent


def dispatch(event: OrderEvent) -> None:
    """Shared by POST /internal/events (local testing) and the SQS consumer background task."""
    if isinstance(event, OrderPreparingEvent):
        logger.info(
            "Assignment engine triggered | order={} restaurant={} items={}",
            event.order_id,
            event.restaurant_id,
            len(event.items),
        )
        assignment_engine.handle_order_preparing(event)
    elif isinstance(event, OrderCancelledEvent):
        logger.warning(
            "Order cancelled — releasing courier | order={} reason={}",
            event.order_id,
            event.reason,
        )
        assignment_engine.handle_order_cancelled(event)
    elif isinstance(event, OrderStatusReadyEvent):
        logger.info(
            "Order ready for pickup | order={} courier={}",
            event.order_id,
            event.courier_id,
        )
        assignment_engine.handle_order_status_ready(event)
    else:
        logger.warning("Unknown event type received | event_type={} order={}", event.event_type, event.order_id)
