import json
import logging
from src.shared.http.api_response import ok, conflict, internal_error
from src.shared.errors.app_error import AppError, ConflictError

logger = logging.getLogger(__name__)


def handler(event: dict, context) -> dict:
    try:
        order_id = event["pathParameters"]["orderId"]
        body = json.loads(event.get("body") or "{}")
        courier_id = body["courierId"]
        accepted_at = body["acceptedAt"]

        # TODO: conditional DynamoDB write — attribute_not_exists(assignedCourierId)
        # Raises ConflictError if another courier already accepted

        return ok({
            "orderId": order_id,
            "status": "ASSIGNED",
        })
    except ConflictError as e:
        return conflict(e.code, e.message)
    except AppError as e:
        logger.warning("AppError: %s", e.message)
        from src.shared.http.api_response import _error
        return _error(e.status_code, e.code, e.message)
    except Exception:
        logger.exception("Unhandled error in accept_delivery")
        return internal_error()
