from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, Path, Query

from src.modules.couriers.model.courier_state import CourierStatus
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
from src.modules.deliveries.repository import delivery_assignment_repository, restaurant_lookup, stage_audit_repository
from src.modules.events.model.delivery_event import (
    DeliveryCourierAssignedEvent,
    DeliveryDeliveredEvent,
    DeliveryFailedEvent,
    DeliveryPickedUpEvent,
)
from src.modules.events.publisher.delivery_event_publisher import publish_delivery_event
from src.shared.auth.current_courier import get_current_courier_id
from src.shared.errors.app_error import NotFoundError
from src.shared.http.api_response import ok
from src.shared.logger import logger
from src.shared.utils.geo import estimate_minutes_from_distance_km, haversine_distance_km
from src.shared.waze.client import get_travel_time_minutes

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
        restaurant_address=assignment.restaurant_address.model_dump(by_alias=True),
        customer_address=assignment.delivery_address.model_dump(by_alias=True),
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
        restaurant_address=assignment.restaurant_address.model_dump(by_alias=True),
        customer_address=assignment.delivery_address.model_dump(by_alias=True),
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
    location = restaurant_lookup.get_restaurant_location(restaurant_id)
    if location is None:
        logger.warning("Restaurant location unavailable — returning fallback ETA | restaurant={}", restaurant_id)
        result = EtaResponse(
            estimated_delivery_minutes=25,
            restaurant_to_customer_km=3.5,
            calculated_at=datetime.now(UTC),
            source="fallback_distance",
        )
    else:
        restaurant_lat, restaurant_lng = location
        distance_km = haversine_distance_km(restaurant_lat, restaurant_lng, delivery_lat, delivery_lng)
        minutes = get_travel_time_minutes(restaurant_lat, restaurant_lng, delivery_lat, delivery_lng)
        source = "waze"
        if minutes is None:
            minutes = estimate_minutes_from_distance_km(distance_km)
            source = "fallback_distance"
        result = EtaResponse(
            estimated_delivery_minutes=round(minutes),
            restaurant_to_customer_km=round(distance_km, 2),
            calculated_at=datetime.now(UTC),
            source=source,
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
    if delivery_assignment_repository.get(order_id) is None:
        raise NotFoundError(f"No delivery assignment found for order {order_id}")

    # Raises ConflictError (409) on a lost first-writer-wins race — handled by main.py's
    # AppError exception handler.
    assignment = delivery_assignment_repository.accept(order_id, body.courier_id, body.accepted_at)

    courier_service.set_status(body.courier_id, CourierStatus.BUSY, current_order_id=order_id)

    profile = courier_service.get_profile(body.courier_id)
    state = courier_service.get_state(body.courier_id)
    vehicle_type = state.vehicle_type if state else None

    publish_delivery_event(
        DeliveryCourierAssignedEvent(
            event_id=f"evt_{uuid4().hex}",
            timestamp=datetime.now(UTC),
            order_id=order_id,
            courier_id=body.courier_id,
            courier_name=profile.get("name"),
            courier_phone=profile.get("phone"),
            vehicle_type=vehicle_type,
            estimated_pickup_time=assignment.estimated_pickup_time,
            estimated_delivery_time=assignment.estimated_delivery_time,
        )
    )
    logger.success("Courier assigned | order={} courier={}", order_id, body.courier_id)

    return ok(
        AcceptDeliveryResponse(
            order_id=order_id,
            status="ASSIGNED",
            restaurant_address=assignment.restaurant_address.model_dump(by_alias=True),
        )
    )


@router.post("/deliveries/{order_id}/stage", response_model=UpdateDeliveryStageResponse)
async def update_delivery_stage(
    order_id: str = Path(...),
    body: UpdateDeliveryStageRequest = ...,
):
    logger.info("Stage transition requested | order={} new_stage={}", order_id, body.new_stage)
    existing = delivery_assignment_repository.get(order_id)
    if existing is None:
        raise NotFoundError(f"No delivery assignment found for order {order_id}")

    now = datetime.now(UTC)

    if body.new_stage == DeliveryStage.DELIVERED:
        # Terminal DELIVERED only fires once BOTH courier (here) and customer
        # (POST /confirm-delivery) have confirmed — see delivery-service-message-contracts.md §2.
        updated = delivery_assignment_repository.set_courier_confirmed(order_id)
        if updated.customer_confirmed:
            final = delivery_assignment_repository.update_stage(order_id, DeliveryStage.DELIVERED, now)
            stage_audit_repository.record(
                order_id,
                event_type="delivery.status.delivered",
                stage=DeliveryStage.DELIVERED.value,
                previous_stage=existing.stage.value if existing.stage else None,
                actor_id=body.courier_id,
                actor_type="COURIER",
                courier_id=body.courier_id,
                metadata={"courierConfirmed": True, "customerConfirmed": True, "confirmedBy": "COURIER"},
            )
            publish_delivery_event(
                DeliveryDeliveredEvent(
                    event_id=f"evt_{uuid4().hex}",
                    timestamp=now,
                    order_id=order_id,
                    courier_id=body.courier_id,
                    courier_confirmed=True,
                    customer_confirmed=True,
                    confirmed_by="COURIER",
                    actual_delivery_time=now,
                    actor_id=body.courier_id,
                )
            )
            courier_service.set_status(body.courier_id, CourierStatus.AVAILABLE, current_order_id=None)
            logger.success("Delivery completed | order={}", order_id)
            return ok(UpdateDeliveryStageResponse(order_id=order_id, stage=final.stage, updated_at=now))

        logger.info("Courier confirmed delivery — awaiting customer confirmation | order={}", order_id)
        return ok(UpdateDeliveryStageResponse(order_id=order_id, stage=updated.stage, updated_at=now))

    updated = delivery_assignment_repository.update_stage(order_id, body.new_stage, now)
    stage_audit_repository.record(
        order_id,
        event_type=f"delivery.status.{body.new_stage.value.lower()}",
        stage=body.new_stage.value,
        previous_stage=existing.stage.value if existing.stage else None,
        actor_id=body.courier_id,
        actor_type="COURIER",
        courier_id=body.courier_id,
    )

    if body.new_stage == DeliveryStage.PICKED_UP:
        publish_delivery_event(
            DeliveryPickedUpEvent(
                event_id=f"evt_{uuid4().hex}",
                timestamp=now,
                order_id=order_id,
                courier_id=body.courier_id,
                actor_id=body.courier_id,
            )
        )
        logger.info("Stage updated | order={} stage={}", order_id, body.new_stage)
    elif body.new_stage == DeliveryStage.FAILED:
        publish_delivery_event(
            DeliveryFailedEvent(
                event_id=f"evt_{uuid4().hex}",
                timestamp=now,
                order_id=order_id,
                courier_id=body.courier_id,
                failure_reason=body.failure_reason.value if body.failure_reason else "OTHER",
                actor_id=body.courier_id,
            )
        )
        courier_service.set_status(body.courier_id, CourierStatus.AVAILABLE, current_order_id=None)
        logger.warning("Delivery failed | order={} reason={}", order_id, body.failure_reason)

    return ok(UpdateDeliveryStageResponse(order_id=order_id, stage=updated.stage, updated_at=now))


@router.post("/deliveries/{order_id}/confirm-delivery", response_model=UpdateDeliveryStageResponse)
async def confirm_delivery(
    order_id: str = Path(...),
    body: ConfirmDeliveryRequest = ...,
):
    logger.info("Customer delivery confirmation | order={} customer={}", order_id, body.customer_id)
    existing = delivery_assignment_repository.get(order_id)
    if existing is None:
        raise NotFoundError(f"No delivery assignment found for order {order_id}")

    now = datetime.now(UTC)
    updated = delivery_assignment_repository.set_customer_confirmed(order_id)

    if not updated.courier_confirmed:
        logger.info("Customer confirmed delivery — awaiting courier confirmation | order={}", order_id)
        return ok(UpdateDeliveryStageResponse(order_id=order_id, stage=updated.stage, updated_at=now))

    final = delivery_assignment_repository.update_stage(order_id, DeliveryStage.DELIVERED, now)
    stage_audit_repository.record(
        order_id,
        event_type="delivery.status.delivered",
        stage=DeliveryStage.DELIVERED.value,
        previous_stage=existing.stage.value if existing.stage else None,
        actor_id=body.customer_id,
        actor_type="CUSTOMER",
        courier_id=updated.assigned_courier_id,
        metadata={"courierConfirmed": True, "customerConfirmed": True, "confirmedBy": "CUSTOMER"},
    )
    publish_delivery_event(
        DeliveryDeliveredEvent(
            event_id=f"evt_{uuid4().hex}",
            timestamp=now,
            order_id=order_id,
            courier_id=updated.assigned_courier_id or "",
            courier_confirmed=True,
            customer_confirmed=True,
            confirmed_by="CUSTOMER",
            actual_delivery_time=now,
            actor_id=body.customer_id,
        )
    )
    if updated.assigned_courier_id:
        courier_service.set_status(updated.assigned_courier_id, CourierStatus.AVAILABLE, current_order_id=None)
    logger.success("Delivery confirmed by both parties | order={}", order_id)
    return ok(UpdateDeliveryStageResponse(order_id=order_id, stage=final.stage, updated_at=now))
