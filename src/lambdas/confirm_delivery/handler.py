import json
import logging
from src.shared.http.api_response import ok, not_found, internal_error
from src.shared.errors.app_error import AppError, NotFoundError

logger = logging.getLogger(__name__)


def handler(event: dict, context) -> dict:
    try:
        order_id = event["pathParameters"]["orderId"]
        body = json.loads(event.get("body") or "{}")
        customer_id = body["customerId"]

        # TODO: mark customer confirmation on DynamoDB active_orders
        # TODO: if courier also confirmed → transition to DELIVERED and publish SNS event

        from datetime import datetime, timezone
        updated_at = datetime.now(timezone.utc).isoformat()

        return ok({"orderId": order_id, "stage": "DELIVERED", "updatedAt": updated_at})
    except NotFoundError as e:
        return not_found(e.code, e.message)
    except AppError as e:
        logger.warning("AppError: %s", e.message)
        from src.shared.http.api_response import _error
        return _error(e.status_code, e.code, e.message)
    except Exception:
        logger.exception("Unhandled error in confirm_delivery")
        return internal_error()
