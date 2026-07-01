from fastapi import APIRouter, Path

from src.modules.couriers.api.dtos import UpdateGpsRequest
from src.shared.http.api_response import no_content
from src.shared.logger import logger

router = APIRouter(tags=["couriers"])


@router.patch("/couriers/{courier_id}/gps", status_code=204)
async def update_courier_gps(
    courier_id: str = Path(...),
    body: UpdateGpsRequest = ...,
):
    # DEBUG — this endpoint is called every 10 s per courier; INFO would flood production logs
    logger.debug("GPS update | courier={} lat={} lng={} ts={}", courier_id, body.lat, body.lng, body.timestamp)
    # TODO: upsert courier GPS to DynamoDB courier_states.lastLocation
    return no_content()
