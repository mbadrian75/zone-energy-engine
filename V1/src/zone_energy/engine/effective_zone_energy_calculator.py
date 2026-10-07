from math import fsum

from zone_energy.config import EngineConfig
from zone_energy.engine.interaction_time_decay_calculator import InteractionTimeDecayCalculator
from zone_energy.models import InteractionState, Zone


class EffectiveZoneEnergyCalculator:
    """Sum independently decayed finalized interactions without changing history.

    OPEN interactions have no finalized contribution. Undefined closed
    interactions remain in history but do not suppress defined contributions.
    The caller supplies a zone snapshot containing only confirmed events.
    ACTIVE and BROKEN zones retain the same historical energy calculation.
    """

    def __init__(self, config: EngineConfig) -> None:
        self._decay = InteractionTimeDecayCalculator(config)

    def calculate(
        self,
        zone: Zone,
        current_candle_index: int,
        year_candles: int,
    ) -> float | None:
        # Validate time inputs even for an empty zone.
        self._decay.calculate(0, zone.creation_index, current_candle_index, year_candles)
        if current_candle_index < zone.created_at_index:
            raise ValueError("Zone is not confirmed at the requested candle")

        energies = []
        seen = set()
        for interaction in zone.interactions:
            if interaction.zone_id != zone.id:
                raise ValueError("Interaction does not belong to this zone")
            if interaction.id in seen:
                raise ValueError("Duplicate interaction would count evidence twice")
            seen.add(interaction.id)
            if interaction.start_index < zone.creation_index:
                raise ValueError("Interaction starts before its zone exists")
            if interaction.start_index > current_candle_index:
                raise ValueError("Zone snapshot contains a future interaction")
            if interaction.state == InteractionState.OPEN:
                continue
            _, _, energy = self._decay.evaluate(
                interaction, current_candle_index, year_candles,
            )
            if energy is not None:
                energies.append(energy)

        if not energies:
            return None
        try:
            return fsum(energies)
        except OverflowError as error:
            raise ValueError("Effective zone energy exceeds the finite numeric range") from error
