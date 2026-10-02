from dataclasses import dataclass
from enum import Enum


class EngineTimeframe(str, Enum):
    """
    Main timeframes supported by Zone Energy Engine V1.
    """

    H1 = "H1"
    H4 = "H4"
    D1 = "D1"


@dataclass(frozen=True, slots=True)
class EngineConfig:
    """
    Configuration parameters for Zone Energy Engine V1.
    """

    # Main timeframe used by the engine
    timeframe: EngineTimeframe = EngineTimeframe.H1

    # Break barrier
    barrier_exponent: float = 2.0

    # Time decay
    yearly_remaining_weight: float = 0.05

    # Zone boundary matching
    extreme_price_tolerance: float = 0.001