import json
from typing import Any


def ok(body: Any) -> dict:
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }


def created(body: Any) -> dict:
    return {
        "statusCode": 201,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }


def no_content() -> dict:
    return {"statusCode": 204, "headers": {}, "body": ""}


def bad_request(code: str, message: str) -> dict:
    return _error(400, code, message)


def not_found(code: str, message: str) -> dict:
    return _error(404, code, message)


def conflict(code: str, message: str) -> dict:
    return _error(409, code, message)


def internal_error(message: str = "Internal server error") -> dict:
    return _error(500, "INTERNAL_ERROR", message)


def _error(status_code: int, code: str, message: str) -> dict:
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"error": code, "message": message}),
    }
