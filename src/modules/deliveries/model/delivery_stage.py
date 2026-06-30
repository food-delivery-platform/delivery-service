from enum import Enum


class DeliveryStage(str, Enum):
    ASSIGNED = "ASSIGNED"
    PICKED_UP = "PICKED_UP"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"
