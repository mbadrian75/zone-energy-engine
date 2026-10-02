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

    broken_zone_energy_at_break: float
    median_active_zone_energy_at_break: float

    barrier_ratio: float
    barrier_cost: float

    displacement: float
    displacement_ratio: float

    persistence: float | None

    break_evidence: float | None