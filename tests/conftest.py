import os

# Must be set before any `src.*` module is imported — env.py reads these at import time, and
# tests must never require real AWS/Supabase credentials.
os.environ.setdefault("AWS_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("DYNAMODB_TABLE_DELIVERY_ASSIGNMENTS", "delivery_assignments")
os.environ.setdefault("DYNAMODB_TABLE_COURIER_STATES", "courier_states")
os.environ.setdefault("DYNAMODB_TABLE_ORDER_EVENTS", "order_events")
os.environ.setdefault("SNS_TOPIC_ARN_ORDER_EVENTS", "arn:aws:sns:us-east-1:123456789012:order-events")

import boto3
import pytest
from moto import mock_aws


@pytest.fixture
def aws():
    """Mocked DynamoDB tables + SNS topic this service actually owns (never active_orders)."""
    with mock_aws():
        ddb = boto3.client("dynamodb", region_name="us-east-1")
        ddb.create_table(
            TableName="delivery_assignments",
            KeySchema=[{"AttributeName": "order_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "order_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        ddb.create_table(
            TableName="courier_states",
            KeySchema=[{"AttributeName": "courierId", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "courierId", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        ddb.create_table(
            TableName="order_events",
            KeySchema=[
                {"AttributeName": "order_id", "KeyType": "HASH"},
                {"AttributeName": "event_time", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "order_id", "AttributeType": "S"},
                {"AttributeName": "event_time", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        sns = boto3.client("sns", region_name="us-east-1")
        sns.create_topic(Name="order-events")
        yield
