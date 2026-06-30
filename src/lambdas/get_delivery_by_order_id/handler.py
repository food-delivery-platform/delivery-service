import logging
from src.shared.http.api_response import ok, not_found, internal_error
from src.shared.errors.app_error import AppError, NotFoundError

logger = logging.getLogger(__name__)


def handler(event: dict, context) -> dict:
    try:
        order_id = event["pathParameters"]["orderId"]

        # TODO: read active_orders and courier_states from DynamoDB
        # Raise NotFoundError if no assignment exists

        return ok({
            "orderId": order_id,
            "status": "ASSIGNED",
            "courierId": None,
            "courierName": None,
            "courierLastLocation": None,
            "estimatedDeliveryTime": None,
            "assignedAt": None,
            "pickedUpAt": None,
            "deliveredAt": None,
        })
    except NotFoundError as e:
        return not_found(e.code, e.message)
    except AppError as e:
        logger.warning("AppError: %s", e.message)
        from src.shared.http.api_response import _error
        return _error(e.status_code, e.code, e.message)
    except Exception:
        logger.exception("Unhandled error in get_delivery_by_order_id")
        return internal_error()
