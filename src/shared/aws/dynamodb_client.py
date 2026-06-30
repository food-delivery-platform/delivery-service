import boto3
from src.shared.config.env import AWS_REGION

_client = None
_resource = None


def get_client():
    global _client
    if _client is None:
        _client = boto3.client("dynamodb", region_name=AWS_REGION)
    return _client


def get_resource():
    global _resource
    if _resource is None:
        _resource = boto3.resource("dynamodb", region_name=AWS_REGION)
    return _resource


def get_table(table_name: str):
    return get_resource().Table(table_name)
