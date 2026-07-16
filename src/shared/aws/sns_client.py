import json

import boto3

from src.shared.config.env import AWS_REGION
from src.shared.logger import logger

_client = None


def get_client():
    global _client
    if _client is None:
        logger.debug("Initialising SNS client | region={}", AWS_REGION)
        _client = boto3.client("sns", region_name=AWS_REGION)
    return _client


def publish(topic_arn: str, subject: str, message: dict, **kwargs) -> str:
    payload = json.dumps(message)
    logger.info("Publishing SNS event | subject={} topic={}", subject, topic_arn)
    try:
        response = get_client().publish(
            TopicArn=topic_arn,
            Subject=subject,
            Message=payload,
            MessageAttributes={
                "eventType": {
                    "DataType": "String",
                    "StringValue": subject,
                }
            },
            **kwargs,
        )
        message_id = response["MessageId"]
        logger.success("SNS event published | subject={} message_id={}", subject, message_id)
        return message_id
    except Exception:
        logger.exception("Failed to publish SNS event | subject={} topic={}", subject, topic_arn)
        raise
