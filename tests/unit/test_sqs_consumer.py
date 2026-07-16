"""Unit tests for the SQS consumer's dispatch-by-eventType logic (docs/PLAN.md Phase 8),
including the unknown-event-type and malformed-payload paths."""

import json
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from src.modules.events.consumer import sqs_consumer


def _message(body: dict) -> dict:
    return {"MessageId": "msg-1", "ReceiptHandle": "rh-1", "Body": json.dumps(body)}


def test_known_event_type_dispatches_and_deletes():
    body = {
        "eventType": "order.status.ready",
        "eventId": "e1",
        "timestamp": "2026-01-01T00:00:00Z",
        "orderId": "order-1",
        "restaurantId": "rest-1",
        "courierId": "courier-1",
        "actorId": "rest-1",
    }
    with (
        patch("src.modules.events.consumer.sqs_consumer.dispatch") as mock_dispatch,
        patch("src.modules.events.consumer.sqs_consumer.delete_message") as mock_delete,
    ):
        sqs_consumer._process_message(_message(body))
        mock_dispatch.assert_called_once()
        mock_delete.assert_called_once()


def test_unknown_event_type_deletes_without_dispatching():
    body = {"eventType": "order.something_unknown", "orderId": "order-1"}
    with (
        patch("src.modules.events.consumer.sqs_consumer.dispatch") as mock_dispatch,
        patch("src.modules.events.consumer.sqs_consumer.delete_message") as mock_delete,
    ):
        sqs_consumer._process_message(_message(body))
        mock_dispatch.assert_not_called()
        mock_delete.assert_called_once()


def test_malformed_json_raises_and_does_not_delete():
    message = {"MessageId": "msg-1", "ReceiptHandle": "rh-1", "Body": "not valid json"}
    with patch("src.modules.events.consumer.sqs_consumer.delete_message") as mock_delete:
        with pytest.raises(json.JSONDecodeError):
            sqs_consumer._process_message(message)
        mock_delete.assert_not_called()


def test_failed_validation_raises_and_does_not_delete():
    # Known eventType, but missing every other required field.
    body = {"eventType": "order.preparing"}
    with patch("src.modules.events.consumer.sqs_consumer.delete_message") as mock_delete:
        with pytest.raises(ValidationError):
            sqs_consumer._process_message(_message(body))
        mock_delete.assert_not_called()
