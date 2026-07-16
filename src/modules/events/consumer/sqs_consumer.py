import asyncio
import json

from src.modules.events.model.order_event import OrderCancelledEvent, OrderPreparingEvent, OrderStatusReadyEvent
from src.modules.events.service.event_dispatcher import dispatch
from src.shared.aws.sqs_client import delete_message, receive_messages
from src.shared.config.env import SQS_POLL_INTERVAL_SECONDS, SQS_QUEUE_URL_DELIVERY_EVENTS
from src.shared.logger import logger

_EVENT_MODELS = {
    "order.preparing": OrderPreparingEvent,
    "order.cancelled": OrderCancelledEvent,
    "order.status.ready": OrderStatusReadyEvent,
}

_running = False


async def start() -> asyncio.Task:
    global _running
    _running = True
    if not SQS_QUEUE_URL_DELIVERY_EVENTS:
        logger.warning("SQS_QUEUE_URL_DELIVERY_EVENTS not set — consumer loop will idle without polling")
    return asyncio.create_task(_poll_loop())


def stop() -> None:
    global _running
    _running = False


async def _poll_loop() -> None:
    while _running:
        if SQS_QUEUE_URL_DELIVERY_EVENTS:
            await _poll_once()
        await asyncio.sleep(SQS_POLL_INTERVAL_SECONDS)


async def _poll_once() -> None:
    messages = await asyncio.to_thread(receive_messages, SQS_QUEUE_URL_DELIVERY_EVENTS, 10, SQS_POLL_INTERVAL_SECONDS)
    for message in messages:
        try:
            _process_message(message)
        except Exception:
            # Malformed payload — leave it in the queue; SQS redelivers up to the DLQ threshold.
            logger.exception(
                "Failed to process SQS message — leaving for redelivery | message_id={}",
                message.get("MessageId", "unknown"),
            )


def _process_message(message: dict) -> None:
    body = json.loads(message["Body"])
    event_type = body.get("eventType")
    model = _EVENT_MODELS.get(event_type)
    if model is None:
        # Unknown event type is not retryable — delete so it doesn't loop forever.
        logger.warning("Unknown SQS event type — deleting | type={}", event_type)
        delete_message(SQS_QUEUE_URL_DELIVERY_EVENTS, message["ReceiptHandle"])
        return

    event = model.model_validate(body)
    dispatch(event)
    delete_message(SQS_QUEUE_URL_DELIVERY_EVENTS, message["ReceiptHandle"])
