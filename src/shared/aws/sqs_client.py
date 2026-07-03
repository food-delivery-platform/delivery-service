import json

import boto3

from src.shared.config.env import AWS_REGION, SQS_QUEUE_URL_DELIVERY_EVENTS
from src.shared.logger import logger

_client = None


def get_client():
    global _client
    if _client is None:
        logger.debug("Initialising SQS client | region={}", AWS_REGION)
        _client = boto3.client("sqs", region_name=AWS_REGION)
    return _client


def delete_message(receipt_handle: str, queue_url: str = SQS_QUEUE_URL_DELIVERY_EVENTS) -> None:
    logger.debug("Deleting SQS message | queue={}", queue_url)
    get_client().delete_message(QueueUrl=queue_url, ReceiptHandle=receipt_handle)


def parse_sqs_records(event: dict) -> list[dict]:
    records = event.get("Records", [])
    logger.debug("Parsing SQS batch | count={}", len(records))
    parsed = []
    for record in records:
        try:
            parsed.append(json.loads(record["body"]))
        except (json.JSONDecodeError, KeyError):
            logger.warning("Failed to parse SQS record | message_id={}", record.get("messageId", "unknown"))
    return parsed
