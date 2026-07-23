import asyncio
import contextlib
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from src.api.routes import couriers, deliveries, events, health
from src.modules.couriers.service import gps_sync_scheduler
from src.modules.events.consumer import sqs_consumer
from src.shared.config.env import (
    GPS_SYNC_INTERVAL_SECONDS,
    SQS_POLL_INTERVAL_SECONDS,
    SQS_QUEUE_URL_DELIVERY_EVENTS,
)
from src.shared.errors.app_error import AppError
from src.shared.logger import logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Delivery Service starting up")
    logger.info(
        "GPS sync scheduler configured — interval={}s (DynamoDB → Postgres courier_locations)",
        GPS_SYNC_INTERVAL_SECONDS,
    )
    logger.info(
        "SQS consumer configured — queue={} poll_interval={}s",
        SQS_QUEUE_URL_DELIVERY_EVENTS or "<not set>",
        SQS_POLL_INTERVAL_SECONDS,
    )
    gps_sync_scheduler.start()
    sqs_task = await sqs_consumer.start()
    logger.success("Delivery Service ready to accept requests")

    yield

    logger.info("Delivery Service shutting down")
    gps_sync_scheduler.stop()
    sqs_consumer.stop()
    sqs_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await sqs_task
    logger.info("Delivery Service stopped")


app = FastAPI(
    title="Delivery Service",
    description="GPS collection, courier assignment, delivery stage tracking, and ETA calculation.",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(health.router)
app.include_router(deliveries.router, prefix="/api/v1")
app.include_router(couriers.router, prefix="/api/v1")
app.include_router(events.router, prefix="/internal")


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    logger.warning("AppError | code={} status={} message={}", exc.code, exc.status_code, exc.message)
    return JSONResponse(status_code=exc.status_code, content={"error": exc.code, "message": exc.message})
