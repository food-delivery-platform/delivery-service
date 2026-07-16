from apscheduler.schedulers.asyncio import AsyncIOScheduler

from src.shared.aws.dynamodb_client import get_table
from src.shared.config.env import DYNAMODB_TABLE_COURIER_STATES, GPS_SYNC_INTERVAL_SECONDS
from src.shared.db.supabase_client import get_client
from src.shared.logger import logger

_scheduler: AsyncIOScheduler | None = None


def sync_once() -> int:
    """Full scan of courier_states -> batch upsert Supabase courier_locations (PostGIS), via an
    `upsert_courier_locations(rows)` RPC — like nearest_couriers, this RPC and the underlying
    table don't exist in database_rel yet (real, currently-open cross-repo gap).

    A full scan every GPS_SYNC_INTERVAL_SECONDS (default 10 min) is the pragmatic MVP approach:
    GSI_couriers_by_status doesn't index on updatedAt globally, so an incremental "changed since
    last run" query isn't cheaply available without a new GSI. Revisit if courier_states grows
    large enough for a full scan every 10 min to become a real cost concern.
    """
    table = get_table(DYNAMODB_TABLE_COURIER_STATES)
    items = table.scan().get("Items", [])

    rows = []
    for item in items:
        last_location = item.get("lastLocation")
        if not last_location:
            continue
        rows.append(
            {
                "courier_id": item["courierId"],
                "lat": float(last_location["lat"]),
                "lng": float(last_location["lng"]),
                "updated_at": last_location["updatedAt"],
            }
        )

    if not rows:
        logger.debug("GPS sync: no courier locations to sync")
        return 0

    get_client().rpc("upsert_courier_locations", {"rows": rows}).execute()
    logger.info("GPS sync complete | couriers_synced={}", len(rows))
    return len(rows)


def _run_sync_job() -> None:
    try:
        sync_once()
    except Exception:
        # Caught here (not left to crash the scheduler thread) — Phase 7 wires
        # GpsSyncJobFailureCount at this call site.
        logger.exception("GPS sync job failed — will retry on next interval")


def start() -> AsyncIOScheduler:
    global _scheduler
    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(_run_sync_job, "interval", seconds=GPS_SYNC_INTERVAL_SECONDS, id="gps_sync")
    _scheduler.start()
    logger.info("GPS sync scheduler started | interval={}s", GPS_SYNC_INTERVAL_SECONDS)
    return _scheduler


def stop() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
