from datetime import UTC, datetime

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from src.modules.couriers.service import gps_sync_scheduler
from src.modules.events.consumer import sqs_consumer
from src.shared.logger import logger
from src.shared.waze.client import is_configured as waze_is_configured

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check():
    logger.debug("Health check requested")
    modules = {
        "sqsConsumer": "ready" if sqs_consumer.is_ready() else "error",
        # No external initialization step of its own — ready the moment the app is up.
        "assignmentEngine": "ready",
        "gpsSyncScheduler": "ready" if gps_sync_scheduler.is_ready() else "error",
        "wazeClient": "ready" if waze_is_configured() else "not_configured",
    }
    # "not_configured" is an accepted, documented state (falls back to distance-only ETA/
    # eligibility) — only "error" should mark the service degraded.
    is_degraded = "error" in modules.values()
    body = {
        "status": "degraded" if is_degraded else "ok",
        "modules": modules,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    if is_degraded:
        return JSONResponse(status_code=503, content=body)
    return body
