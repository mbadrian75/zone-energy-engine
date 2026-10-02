from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BreakRecord:
    """
    Immutable snapshot of a valid zone break.
    """

    broken_zone_id: int

    break_index: int
    break_close: float

    break_time_from_origin: int

    broken_zone_energy_at_break: float | None
    median_active_zone_energy_at_break: float | None

    barrier_ratio: float | None
    barrier_cost: float | None

    displacement: float
    displacement_ratio: float

    persistence: float | None

    break_evidence: float | None
