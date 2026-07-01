from enum import Enum


class VehicleType(str, Enum):
    BIKE = "bike"
    CAR = "car"
    WALK = "walk"
