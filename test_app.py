import importlib
import json
import os
from unittest.mock import Mock, patch

import pytest


@pytest.fixture(scope="module")
def service():
    with patch.dict(
        os.environ,
        {
            "AWS_REGION": "us-east-1",
            "AWS_SQS_URL": "https://sqs.example.test/queue",
            "AWS_DYNAMODB_TABLE": "evaluation-events",
        },
    ), patch("boto3.Session") as session_factory, patch("threading.Thread"):
        session_factory.return_value.client.side_effect = [Mock(), Mock()]
        return importlib.import_module("app")


def test_health_returns_ok(service):
    response = service.app.test_client().get("/health")

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_process_message_stores_event_and_deletes_message(service):
    service.dynamodb_client = Mock()
    service.sqs_client = Mock()
    message = {
        "MessageId": "message-1",
        "ReceiptHandle": "receipt-1",
        "Body": json.dumps(
            {
                "user_id": "user-123",
                "flag_name": "new-ui",
                "result": True,
                "timestamp": "2026-01-01T00:00:00Z",
            }
        ),
    }

    service.process_message(message)

    item = service.dynamodb_client.put_item.call_args.kwargs
    assert item["TableName"] == "evaluation-events"
    assert item["Item"]["user_id"] == {"S": "user-123"}
    assert item["Item"]["flag_name"] == {"S": "new-ui"}
    assert item["Item"]["result"] == {"S": "True"}
    assert item["Item"]["timestamp"] == {"S": "2026-01-01T00:00:00Z"}
    assert item["Item"]["event_id"]["S"]
    service.sqs_client.delete_message.assert_called_once_with(
        QueueUrl="https://sqs.example.test/queue",
        ReceiptHandle="receipt-1",
    )


def test_process_message_does_not_delete_when_storage_fails(service):
    service.dynamodb_client = Mock()
    service.dynamodb_client.put_item.side_effect = RuntimeError("storage unavailable")
    service.sqs_client = Mock()
    message = {
        "MessageId": "message-1",
        "ReceiptHandle": "receipt-1",
        "Body": json.dumps(
            {
                "user_id": "user-123",
                "flag_name": "new-ui",
                "result": True,
                "timestamp": "2026-01-01T00:00:00Z",
            }
        ),
    }

    service.process_message(message)

    service.sqs_client.delete_message.assert_not_called()


def test_process_message_does_not_delete_invalid_json(service):
    service.dynamodb_client = Mock()
    service.sqs_client = Mock()
    message = {
        "MessageId": "message-1",
        "ReceiptHandle": "receipt-1",
        "Body": "{invalid",
    }

    service.process_message(message)

    service.dynamodb_client.put_item.assert_not_called()
    service.sqs_client.delete_message.assert_not_called()
