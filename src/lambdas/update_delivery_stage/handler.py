import json
import logging
from src.shared.http.api_response import ok, bad_request, not_found, internal_error
from src.shared.errors.app_error import AppError, NotFoundError, ValidationError

logger = logging.getLogger(__name__)

VALID_STAGES = {"PICKED_UP", "DELIVERED", "FAILED"}


def handler(event: dict, context) -> dict:
    try:
        order_id = event["pathParameters"]["orderId"]
        body = json.loads(event.get("body") or "{}")
        new_stage = body.get("newStage")
        courier_id = body.get("courierId")

        if new_stage not in VALID_STAGES:
            raise ValidationError(f"newStage must be one of {VALID_STAGES}")

        if new_stage == "FAILED" and not body.get("failureReason"):
            raise ValidationError("failureReason is required when newStage is FAILED")

        # TODO: write stage transition to DynamoDB order_events and active_orders
        # TODO: publish delivery event to SNS order-events topic
        # TODO: call Order Service PATCH /orders/{orderId}/status

        from datetime import datetime, timezone
        updated_at = datetime.now(timezone.utc).isoformat()

        return ok({"orderId": order_id, "stage": new_stage, "updatedAt": updated_at})
    except ValidationError as e:
        return bad_request(e.code, e.message)
    except NotFoundError as e:
        return not_found(e.code, e.message)
    except AppError as e:
        logger.warning("AppError: %s", e.message)
        from src.shared.http.api_response import _error
        return _error(e.status_code, e.code, e.message)
    except Exception:
        logger.exception("Unhandled error in update_delivery_stage")
        return internal_error()
