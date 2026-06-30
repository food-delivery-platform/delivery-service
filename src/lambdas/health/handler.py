import logging
from src.shared.http.api_response import ok

logger = logging.getLogger(__name__)


def handler(event: dict, context) -> dict:
    return ok({"status": "ok"})
