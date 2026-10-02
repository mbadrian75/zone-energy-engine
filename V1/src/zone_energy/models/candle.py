from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class Candle:
    """
    Immutable OHLCV candle used by Zone Energy Engine.
    """

    datetime: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    def __post_init__(self) -> None:
        self._validate()

    def _validate(self) -> None:
        if self.high < self.low:
            raise ValueError(
                f"Invalid candle at {self.datetime}: "
                f"high ({self.high}) < low ({self.low})"
            )

        if self.high < max(self.open, self.close):
            raise ValueError(
                f"Invalid candle at {self.datetime}: "
                "high is below open/close"
            )

        if self.low > min(self.open, self.close):
            raise ValueError(
                f"Invalid candle at {self.datetime}: "
                "low is above open/close"
            )

        if self.volume < 0:
            raise ValueError(
                f"Invalid candle at {self.datetime}: "
                f"negative volume ({self.volume})"
            )

    @property
    def is_bullish(self) -> bool:
        return self.close > self.open

    @property
    def is_bearish(self) -> bool:
        return self.close < self.open

    @property
    def is_doji(self) -> bool:
        return self.close == self.open

    @property
    def range(self) -> float:
        return self.high - self.low

    @property
    def body(self) -> float:
        return abs(self.close - self.open)

    @property
    def upper_wick(self) -> float:
        return self.high - max(self.open, self.close)

    @property
    def lower_wick(self) -> float:
        return min(self.open, self.close) - self.low