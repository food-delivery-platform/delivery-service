import json
import boto3
from src.shared.config.env import AWS_REGION, SNS_TOPIC_ARN_ORDER_EVENTS

_client = None


def get_client():
    global _client
    if _client is None:
        _client = boto3.client("sns", region_name=AWS_REGION)
    return _client


def publish_order_event(event_type: str, payload: dict) -> str:
    message = json.dumps({**payload, "eventType": event_type})
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
    return response["MessageId"]
