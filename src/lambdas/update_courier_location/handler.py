import json
import logging
from src.shared.http.api_response import no_content, bad_request, internal_error
from src.shared.errors.app_error import AppError, ValidationError

logger = logging.getLogger(__name__)


def handler(event: dict, context) -> dict:
    try:
        courier_id = event["pathParameters"]["courierId"]
        body = json.loads(event.get("body") or "{}")
        lat = body.get("lat")
        lng = body.get("lng")
        timestamp = body.get("timestamp")

        if lat is None or lng is None:
            raise ValidationError("lat and lng are required")

        # TODO: upsert courier GPS to DynamoDB courier_states.lastLocation

        return no_content()
    except ValidationError as e:
        return bad_request(e.code, e.message)
    except AppError as e:
        logger.warning("AppError: %s", e.message)
        from src.shared.http.api_response import _error
        return _error(e.status_code, e.code, e.message)
    except Exception:
        logger.exception("Unhandled error in update_courier_location")
        return internal_error()
