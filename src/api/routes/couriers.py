from fastapi import APIRouter, Path

from src.modules.couriers.api.dtos import CourierProfileResponse, UpdateGpsRequest
from src.modules.couriers.service import courier_service
from src.shared.http.api_response import no_content, ok
from src.shared.logger import logger

router = APIRouter(tags=["couriers"])


@router.patch("/couriers/{courier_id}/gps", status_code=204)
async def update_courier_gps(
    courier_id: str = Path(...),
    body: UpdateGpsRequest = ...,
):
    # DEBUG — this endpoint is called every 10 s per courier; INFO would flood production logs
    logger.debug("GPS update | courier={} lat={} lng={} ts={}", courier_id, body.lat, body.lng, body.timestamp)
    courier_service.update_gps(courier_id, body.lat, body.lng, body.timestamp)
    return no_content()


@router.get("/couriers/{courier_id}/profile", response_model=CourierProfileResponse)
async def get_courier_profile(courier_id: str = Path(...)):
    logger.debug("Courier profile requested | courier={}", courier_id)
    profile = courier_service.get_profile(courier_id)
    return ok(CourierProfileResponse(**profile))
