from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.api.routes import couriers, deliveries, events, health
from src.shared.config.env import (
    GPS_SYNC_INTERVAL_SECONDS,
    SQS_POLL_INTERVAL_SECONDS,
    SQS_QUEUE_URL_DELIVERY_EVENTS,
)
from src.shared.logger import logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Delivery Service starting up")
    logger.info(
        "GPS sync scheduler configured — interval={}s (DynamoDB → Supabase courier_locations)",
        GPS_SYNC_INTERVAL_SECONDS,
    )
    logger.info(
        "SQS consumer configured — queue={} poll_interval={}s",
        SQS_QUEUE_URL_DELIVERY_EVENTS or "<not set>",
        SQS_POLL_INTERVAL_SECONDS,
    )
    # TODO: start APScheduler GPS sync job (DynamoDB → Supabase every 10 min)
    # TODO: start SQS polling background task for delivery-events queue
    logger.success("Delivery Service ready to accept requests")

    yield

    logger.info("Delivery Service shutting down")
    # TODO: graceful shutdown — stop scheduler and SQS consumer
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
