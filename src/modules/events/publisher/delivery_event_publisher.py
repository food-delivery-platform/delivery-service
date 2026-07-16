from src.modules.events.model.delivery_event import (
    DeliveryCourierAssignedEvent,
    DeliveryCourierReassignedEvent,
    DeliveryDeliveredEvent,
    DeliveryFailedEvent,
    DeliveryPickedUpEvent,
)
from src.shared.aws.sns_client import publish
from src.shared.config.env import SNS_TOPIC_ARN_ORDER_EVENTS

DeliveryEvent = (
    DeliveryCourierAssignedEvent
    | DeliveryPickedUpEvent
    | DeliveryDeliveredEvent
    | DeliveryFailedEvent
    | DeliveryCourierReassignedEvent
)


def publish_delivery_event(event: DeliveryEvent) -> str:
    return publish(SNS_TOPIC_ARN_ORDER_EVENTS, event.event_type, event.model_dump(mode="json", by_alias=True))
