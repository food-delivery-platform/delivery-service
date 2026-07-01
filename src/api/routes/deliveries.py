from datetime import UTC, datetime

from fastapi import APIRouter, Path, Query

from src.modules.deliveries.api.dtos import (
    AcceptDeliveryRequest,
    AcceptDeliveryResponse,
    AvailableDeliveriesResponse,
    ConfirmDeliveryRequest,
    DeliveryStateResponse,
    EtaResponse,
    UpdateDeliveryStageRequest,
    UpdateDeliveryStageResponse,
)
from src.modules.deliveries.model.delivery_stage import DeliveryStage
from src.shared.http.api_response import ok
from src.shared.logger import logger

router = APIRouter(tags=["deliveries"])


@router.get("/deliveries/eta", response_model=EtaResponse)
async def get_delivery_eta(
    restaurant_id: str = Query(..., alias="restaurantId"),
    delivery_lat: float = Query(..., alias="deliveryLat"),
    delivery_lng: float = Query(..., alias="deliveryLng"),
):
    logger.info(
        "ETA requested | restaurant={} delivery_lat={} delivery_lng={}",
        restaurant_id,
        delivery_lat,
        delivery_lng,
    )
    # TODO: call Waze API for restaurant → customer travel time
    # TODO: remove fallback_distance source once Waze is wired up
    logger.warning("Waze client not implemented — returning distance-based ETA fallback")
    result = EtaResponse(
        estimated_delivery_minutes=25,
        restaurant_to_customer_km=3.5,
        calculated_at=datetime.now(UTC),
        source="fallback_distance",
    )
    logger.debug(
        "ETA result | restaurant={} estimated_minutes={} source={}",
        restaurant_id,
        result.estimated_delivery_minutes,
        result.source,
    )
    return ok(result)


@router.get("/deliveries/available", response_model=AvailableDeliveriesResponse)
async def get_available_deliveries():
    # DEBUG — polled every 30 s by every courier; INFO would be extremely noisy
    logger.debug("Available deliveries polled")
    # TODO: extract courierId from JWT; query DynamoDB active_orders where eligible_courier_ids contains courierId
    return ok(AvailableDeliveriesResponse(available_orders=[]))


@router.get("/deliveries/{order_id}", response_model=DeliveryStateResponse)
async def get_delivery(order_id: str = Path(...)):
    # DEBUG — polled every 5 s by the Customer App during active delivery
    logger.debug("Delivery state requested | order={}", order_id)
    # TODO: read active_orders and courier_states from DynamoDB; raise 404 if not found
    return ok(DeliveryStateResponse(order_id=order_id, status="ASSIGNED"))


@router.post("/deliveries/{order_id}/accept", response_model=AcceptDeliveryResponse)
async def accept_delivery(
    order_id: str = Path(...),
    body: AcceptDeliveryRequest = ...,
):
    logger.info("Courier accept attempt | order={} courier={}", order_id, body.courier_id)
    # TODO: conditional DynamoDB write — attribute_not_exists(assignedCourierId)
    # TODO: on ConflictError → logger.warning("Accept rejected — order already assigned | "
    #     "order={} courier={}", order_id, body.courier_id)
    # TODO: on success  → logger.success("Courier assigned | order={} courier={}", order_id, body.courier_id)
    return ok(AcceptDeliveryResponse(order_id=order_id, status="ASSIGNED"))


@router.post("/deliveries/{order_id}/stage", response_model=UpdateDeliveryStageResponse)
async def update_delivery_stage(
    order_id: str = Path(...),
    body: UpdateDeliveryStageRequest = ...,
):
    logger.info("Stage transition requested | order={} new_stage={}", order_id, body.new_stage)
    # TODO: write transition to DynamoDB order_events + active_orders
    # TODO: publish delivery event to SNS order-events topic
    # TODO: PATCH /orders/{orderId}/status on Order Service

    updated_at = datetime.now(UTC)

    if body.new_stage == DeliveryStage.DELIVERED:
        logger.success("Delivery completed | order={}", order_id)
    elif body.new_stage == DeliveryStage.FAILED:
        logger.warning(
            "Delivery failed | order={} reason={}",
            order_id,
            body.failure_reason,
        )
    else:
        logger.info("Stage updated | order={} stage={}", order_id, body.new_stage)

    return ok(UpdateDeliveryStageResponse(order_id=order_id, stage=body.new_stage, updated_at=updated_at))


@router.post("/deliveries/{order_id}/confirm-delivery", response_model=UpdateDeliveryStageResponse)
async def confirm_delivery(
    order_id: str = Path(...),
    body: ConfirmDeliveryRequest = ...,
):
    logger.info("Customer delivery confirmation | order={} customer={}", order_id, body.customer_id)
    # TODO: mark customer confirmation on DynamoDB active_orders
    # TODO: if courier also confirmed → transition to DELIVERED, publish SNS event
    # TODO: on both confirmed → logger.success("Delivery confirmed by both parties | order={}", order_id)
    return ok(
        UpdateDeliveryStageResponse(
            order_id=order_id,
            stage=DeliveryStage.DELIVERED,
            updated_at=datetime.now(UTC),
        )
    )
