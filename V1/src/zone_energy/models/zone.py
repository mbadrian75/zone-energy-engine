from dataclasses import dataclass, field

from .enums import PriceSide, ZoneState, ZoneType
from .interaction import Interaction


@dataclass(slots=True)
class Zone:
    """
    Support or resistance zone tracked by the engine.
    """

    id: int

    type: ZoneType
    state: ZoneState

    lower_price: float
    upper_price: float

    creation_extreme: float
    creation_index: int

    interactions: list[Interaction] = field(default_factory=list)

    previous_zone_id: int | None = None

    created_at_index: int = 0

    last_interaction_origin_index: int | None = None

    last_external_price_side: PriceSide | None = None

    def __post_init__(self) -> None:
        self._validate()

    def _validate(self) -> None:
        if self.upper_price <= self.lower_price:
            raise ValueError(
                f"Invalid zone {self.id}: "
                f"upper_price ({self.upper_price}) must be greater than "
                f"lower_price ({self.lower_price})"
            )

        if self.creation_index < 0:
            raise ValueError(
                f"Invalid zone {self.id}: "
                f"creation_index cannot be negative"
            )

        if self.created_at_index < 0:
            raise ValueError(
                f"Invalid zone {self.id}: "
                f"created_at_index cannot be negative"
            )

    @property
    def height(self) -> float:
        return self.upper_price - self.lower_price