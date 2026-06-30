from enum import Enum


class CourierStatus(str, Enum):
    OFFLINE = "offline"
    AVAILABLE = "available"
    BUSY = "busy"
