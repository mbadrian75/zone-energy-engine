from dataclasses import dataclass, field

from .break_record import BreakRecord
from .enums import InteractionState


@dataclass(slots=True)
class Interaction:
    """
    A movement originating from a zone interaction.
    """

    id: int
    zone_id: int

    state: InteractionState

    start_price: float
    start_index: int

    end_price: float | None = None
    end_index: int | None = None

    distance: float | None = None
    movement_time: int | None = None

    previous_distance: float | None = None
    previous_movement_time: int | None = None

    breaks: list[BreakRecord] = field(default_factory=list)

    movement_energy: float | None = None
    total_break_evidence: float | None = None

    base_energy: float | None = None