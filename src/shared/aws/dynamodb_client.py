import boto3

from src.shared.config.env import AWS_REGION
from src.shared.logger import logger

_client = None
_resource = None


def get_client():
    global _client
    if _client is None:
        logger.debug("Initialising DynamoDB client | region={}", AWS_REGION)
        _client = boto3.client("dynamodb", region_name=AWS_REGION)
    return _client


def get_resource():
    global _resource
    if _resource is None:
        logger.debug("Initialising DynamoDB resource | region={}", AWS_REGION)
        _resource = boto3.resource("dynamodb", region_name=AWS_REGION)
    return _resource


def get_table(table_name: str):
    logger.debug("Resolving DynamoDB table | table={}", table_name)
    return get_resource().Table(table_name)
