from datetime import UTC, datetime

from fastapi import APIRouter

from src.shared.logger import logger

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check():
    logger.debug("Health check requested")
    return {
        "status": "ok",
        "modules": {
            "sqsConsumer": "ready",
            "assignmentEngine": "ready",
            "gpsSyncScheduler": "ready",
            "wazeClient": "ready",
        },
        "timestamp": datetime.now(UTC).isoformat(),
    }
