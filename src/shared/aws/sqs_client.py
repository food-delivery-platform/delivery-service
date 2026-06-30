import json
import boto3
from src.shared.config.env import AWS_REGION, SQS_QUEUE_URL_DELIVERY_EVENTS

_client = None


def get_client():
    global _client
    if _client is None:
        _client = boto3.client("sqs", region_name=AWS_REGION)
    return _client


def delete_message(receipt_handle: str, queue_url: str = SQS_QUEUE_URL_DELIVERY_EVENTS) -> None:
    get_client().delete_message(QueueUrl=queue_url, ReceiptHandle=receipt_handle)


def parse_sqs_records(event: dict) -> list[dict]:
    return [json.loads(record["body"]) for record in event.get("Records", [])]
