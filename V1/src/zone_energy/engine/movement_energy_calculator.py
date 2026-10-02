from math import isfinite

from zone_energy.models import Interaction, InteractionState


class MovementEnergyCalculator:
    """Calculate relative movement energy; bootstrap has no relative value."""

    @staticmethod
    def calculate(
        distance: float,
        movement_time: int,
        previous_distance: float | None,
        previous_movement_time: int | None,
    ) -> float | None:
        for name, value in (
            ("distance", distance),
            ("movement_time", movement_time),
            ("previous_distance", previous_distance),
            ("previous_movement_time", previous_movement_time),
        ):
            if value is None:
                if name in ("distance", "movement_time"):
                    raise ValueError(f"{name} is required")
                continue
            if not isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and greater than zero")

        if previous_distance is None and previous_movement_time is None:
            return None
        if previous_distance is None or previous_movement_time is None:
            raise ValueError("Previous move requires both distance and time")

        energy = (
            (distance / previous_distance)
            * (previous_movement_time / movement_time)
        )
        if not isfinite(energy) or energy <= 0:
            raise ValueError("Movement energy is outside the representable positive range")
        return energy

    @staticmethod
    def apply(interaction: Interaction) -> float | None:
        """Store energy on a closed interaction without altering other evidence."""
        if interaction.state != InteractionState.CLOSED:
            raise ValueError("Movement energy requires a CLOSED interaction")
        energy = MovementEnergyCalculator.calculate(
            distance=interaction.distance,
            movement_time=interaction.movement_time,
            previous_distance=interaction.previous_distance,
            previous_movement_time=interaction.previous_movement_time,
        )
        interaction.movement_energy = energy
        return energy
