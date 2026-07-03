import json

import boto3

from src.shared.config.env import AWS_REGION, SNS_TOPIC_ARN_ORDER_EVENTS
from src.shared.logger import logger

_client = None


def get_client():
    global _client
    if _client is None:
        logger.debug("Initialising SNS client | region={}", AWS_REGION)
        _client = boto3.client("sns", region_name=AWS_REGION)
    return _client


def publish_order_event(event_type: str, payload: dict) -> str:
    message = json.dumps({**payload, "eventType": event_type})
    logger.info("Publishing SNS event | type={} topic={}", event_type, SNS_TOPIC_ARN_ORDER_EVENTS)
    try:
        response = get_client().publish(
            TopicArn=SNS_TOPIC_ARN_ORDER_EVENTS,
            Message=message,
            MessageAttributes={
                "eventType": {
                    "DataType": "String",
                    "StringValue": event_type,
                }
            },
        )
        message_id = response["MessageId"]
        logger.success("SNS event published | type={} message_id={}", event_type, message_id)
        return message_id
    except Exception:
        logger.exception("Failed to publish SNS event | type={} topic={}", event_type, SNS_TOPIC_ARN_ORDER_EVENTS)
        raise
