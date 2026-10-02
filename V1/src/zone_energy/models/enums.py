from enum import Enum


class ZoneType(str, Enum):
    SUPPORT = "support"
    RESISTANCE = "resistance"


class ZoneState(str, Enum):
    ACTIVE = "active"
    BROKEN = "broken"


class InteractionState(str, Enum):
    OPEN = "open"
    CLOSED = "closed"

class PriceSide(str, Enum):
    ABOVE = "above"
    BELOW = "below"
    INSIDE = "inside"