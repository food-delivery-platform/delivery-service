import boto3

from src.shared.config.env import AWS_REGION, ENVIRONMENT
from src.shared.logger import logger

_NAMESPACE = "FoodDelivery/DeliveryService"
_client = None


def get_client():
    global _client
    if _client is None:
        _client = boto3.client("cloudwatch", region_name=AWS_REGION)
    return _client


def put_metric(metric_name: str, value: float, unit: str) -> None:
    try:
        get_client().put_metric_data(
            Namespace=_NAMESPACE,
            MetricData=[
                {
                    "MetricName": metric_name,
                    "Value": value,
                    "Unit": unit,
                    "Dimensions": [{"Name": "Environment", "Value": ENVIRONMENT}],
                }
            ],
        )
    except Exception:
        # Metrics are best-effort — never let a CloudWatch outage break the request/job that
        # triggered it.
        logger.exception("Failed to publish CloudWatch metric | metric={}", metric_name)


def courier_assignment_lag_seconds(value: float) -> None:
    put_metric("CourierAssignmentLagSeconds", value, "Seconds")


def stage_machine_error_count(value: int = 1) -> None:
    put_metric("StageMachineErrorCount", value, "Count")


def gps_sync_job_failure_count(value: int = 1) -> None:
    put_metric("GpsSyncJobFailureCount", value, "Count")


def waze_api_error_rate(value: float) -> None:
    """0 or 100 per call — CloudWatch's own 5-minute average turns this into the alarm's
    percentage, per delivery-service-message-contracts.md §6."""
    put_metric("WazeApiErrorRate", value, "Percent")


def eligible_couriers_found(value: int) -> None:
    put_metric("EligibleCouriersFound", value, "Count")


# UnacceptedOrdersCount is intentionally not wired here: it's a periodic aggregate ("orders still
# unaccepted after N minutes") with no natural per-event call site in Phases 4-6 — that shape of
# job belongs to a scheduled monitoring pass (Monitoring Service, per platform ARCHITECTURE.md
# §4.2), not something this service's own request/event handlers can emit inline.
