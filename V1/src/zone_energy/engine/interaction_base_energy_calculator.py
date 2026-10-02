from collections.abc import Iterable
from math import fsum, isfinite

from zone_energy.models import Interaction, InteractionState


class InteractionBaseEnergyCalculator:
    """Aggregate break evidence and finalize a closed interaction's base energy."""

    @staticmethod
    def calculate(
        movement_energy: float | None,
        break_evidence: Iterable[float | None],
    ) -> tuple[float | None, float | None]:
        if movement_energy is not None:
            if not isfinite(movement_energy) or movement_energy <= 0:
                raise ValueError("movement_energy must be finite and greater than zero")

        evidence = []
        missing = False
        for value in break_evidence:
            if value is None:
                missing = True
            elif not isfinite(value) or value < 0:
                raise ValueError("break_evidence must be finite and nonnegative")
            else:
                evidence.append(value)

        # Undefined evidence must not be silently counted as zero.
        if missing:
            return None, None
        try:
            total = fsum(evidence)
            base = None if movement_energy is None else fsum((movement_energy, total))
        except OverflowError as error:
            raise ValueError("Interaction energy exceeds the finite numeric range") from error
        return total, base

    @staticmethod
    def apply(interaction: Interaction) -> tuple[float | None, float | None]:
        if interaction.state != InteractionState.CLOSED:
            raise ValueError("Base energy requires a CLOSED interaction")
        if interaction.base_energy is not None:
            raise ValueError("Historical base energy has already been finalized")

        total, base = InteractionBaseEnergyCalculator.calculate(
            movement_energy=interaction.movement_energy,
            break_evidence=(record.break_evidence for record in interaction.breaks),
        )
        interaction.total_break_evidence = total
        interaction.base_energy = base
        return total, base
