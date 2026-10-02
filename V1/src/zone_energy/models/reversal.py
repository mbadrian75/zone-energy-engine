from dataclasses import dataclass

from .enums import ZoneType


@dataclass(frozen=True, slots=True)
class Reversal:
    """
    Confirmed three-candle reversal.

    The reversal is detected when C3 closes,
    while its historical origin is C2.
    """

    type: ZoneType

    extreme_price: float
    extreme_index: int

    detection_index: int