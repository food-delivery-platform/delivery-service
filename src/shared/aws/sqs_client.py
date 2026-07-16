import boto3

from src.shared.config.env import AWS_REGION
from src.shared.logger import logger

_client = None


def get_client():
    global _client
    if _client is None:
        logger.debug("Initialising SQS client | region={}", AWS_REGION)
        _client = boto3.client("sqs", region_name=AWS_REGION)
    return _client


def receive_messages(queue_url: str, max_messages: int = 10, wait_seconds: int = 5) -> list[dict]:
    logger.debug("Polling SQS | queue={} max_messages={} wait_seconds={}", queue_url, max_messages, wait_seconds)
    response = get_client().receive_message(
        QueueUrl=queue_url,
        MaxNumberOfMessages=max_messages,
        WaitTimeSeconds=wait_seconds,
    )
    messages = response.get("Messages", [])
    logger.debug("SQS poll returned | queue={} count={}", queue_url, len(messages))
    return messages


def delete_message(queue_url: str, receipt_handle: str) -> None:
    logger.debug("Deleting SQS message | queue={}", queue_url)
    get_client().delete_message(QueueUrl=queue_url, ReceiptHandle=receipt_handle)
