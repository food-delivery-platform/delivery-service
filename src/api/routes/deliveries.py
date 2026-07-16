from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Path, Query

from src.modules.couriers.service import courier_service
from src.modules.deliveries.api.dtos import (
    AcceptDeliveryRequest,
    AcceptDeliveryResponse,
    AvailableDeliveriesResponse,
    AvailableOrder,
    AvailableOrderItem,
    ConfirmDeliveryRequest,
    CourierLastLocation,
    DeliveryStateResponse,
    EtaResponse,
    UpdateDeliveryStageRequest,
    UpdateDeliveryStageResponse,
)
from src.modules.deliveries.model.delivery_assignment import DeliveryAssignment
from src.modules.deliveries.model.delivery_stage import DeliveryStage
from src.modules.deliveries.repository import delivery_assignment_repository, restaurant_lookup
from src.shared.auth.current_courier import get_current_courier_id
from src.shared.errors.app_error import NotFoundError
from src.shared.http.api_response import ok
from src.shared.logger import logger

router = APIRouter(tags=["deliveries"])


def _minutes_from_now(at: datetime | None) -> int | None:
    if at is None:
        return None
    target = at if at.tzinfo else at.replace(tzinfo=UTC)
    return max(0, round((target - datetime.now(UTC)).total_seconds() / 60))


def _to_available_order(assignment: DeliveryAssignment) -> AvailableOrder:
    return AvailableOrder(
        order_id=assignment.order_id,
        restaurant_id=assignment.restaurant_id,
        restaurant_name=restaurant_lookup.get_restaurant_name(assignment.restaurant_id),
        restaurant_address=assignment.restaurant_address.model_dump(),
        customer_address=assignment.delivery_address.model_dump(),
        estimated_pickup_minutes=_minutes_from_now(assignment.estimated_pickup_time),
        estimated_delivery_minutes=_minutes_from_now(assignment.estimated_delivery_time),
        estimated_earnings=None,  # no earnings formula defined anywhere yet — see docs/PLAN.md Phase 3
        currency=assignment.currency,
        items=[
            AvailableOrderItem(name=item.get("name", ""), quantity=item.get("quantity", 1)) for item in assignment.items
        ],
    )


def _to_delivery_state_response(assignment: DeliveryAssignment) -> DeliveryStateResponse:
    courier_name = courier_phone = None
    courier_last_location = None
    if assignment.assigned_courier_id:
        profile = courier_service.get_profile(assignment.assigned_courier_id)
        courier_name = profile.get("name")
        courier_phone = profile.get("phone")
        state = courier_service.get_state(assignment.assigned_courier_id)
        if state and state.last_location:
            courier_last_location = CourierLastLocation(
                lat=state.last_location.lat,
                lng=state.last_location.lng,
                updated_at=state.last_location.updated_at,
            )
    return DeliveryStateResponse(
        order_id=assignment.order_id,
        status=assignment.stage.value if assignment.stage else "PENDING_ASSIGNMENT",
        courier_id=assignment.assigned_courier_id,
        courier_name=courier_name,
        courier_phone=courier_phone,
        courier_last_location=courier_last_location,
        restaurant_name=restaurant_lookup.get_restaurant_name(assignment.restaurant_id),
        restaurant_address=assignment.restaurant_address.model_dump(),
        customer_address=assignment.delivery_address.model_dump(),
        estimated_delivery_time=assignment.estimated_delivery_time,
        assigned_at=assignment.assigned_at,
        picked_up_at=assignment.picked_up_at,
        delivered_at=assignment.delivered_at,
    )


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
async def get_available_deliveries(courier_id: str | None = Depends(get_current_courier_id)):
    # DEBUG — polled every 30 s by every courier; INFO would be extremely noisy
    logger.debug("Available deliveries polled | courier={}", courier_id)
    if courier_id is None:
        return ok(AvailableDeliveriesResponse(available_orders=[]))
    assignments = delivery_assignment_repository.list_eligible_for_courier(courier_id)
    return ok(AvailableDeliveriesResponse(available_orders=[_to_available_order(a) for a in assignments]))


@router.get("/deliveries/{order_id}", response_model=DeliveryStateResponse)
async def get_delivery(order_id: str = Path(...)):
    # DEBUG — polled every 5 s by the Customer App during active delivery
    logger.debug("Delivery state requested | order={}", order_id)
    assignment = delivery_assignment_repository.get(order_id)
    if assignment is None:
        raise NotFoundError(f"No delivery assignment found for order {order_id}")
    return ok(_to_delivery_state_response(assignment))


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
