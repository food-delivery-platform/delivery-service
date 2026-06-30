import logging
from src.shared.http.api_response import ok, internal_error
from src.shared.errors.app_error import AppError

logger = logging.getLogger(__name__)


def handler(event: dict, context) -> dict:
    try:
        courier_id = event["requestContext"]["authorizer"]["claims"]["sub"]

        # TODO: query DynamoDB active_orders where eligible_courier_ids contains courier_id
        available_orders = []

        return ok({"availableOrders": available_orders})
    except AppError as e:
        logger.warning("AppError: %s", e.message)
        from src.shared.http.api_response import _error
        return _error(e.status_code, e.code, e.message)
    except Exception:
        logger.exception("Unhandled error in get_available_deliveries")
        return internal_error()
