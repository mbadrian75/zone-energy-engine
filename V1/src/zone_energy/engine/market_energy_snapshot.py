from collections.abc import Iterable
from dataclasses import dataclass
from statistics import median

from zone_energy.config import EngineConfig
from zone_energy.engine.effective_zone_energy_calculator import EffectiveZoneEnergyCalculator
from zone_energy.engine.interaction_time_decay_calculator import InteractionTimeDecayCalculator
from zone_energy.models import Zone, ZoneState


@dataclass(frozen=True, slots=True)
class MarketEnergySnapshot:
    """Immutable numeric snapshot of ACTIVE zones before a candle's breaks."""

    candle_index: int
    zone_energies: tuple[tuple[int, float | None], ...]
    median_active_energy: float | None

    def reference_for_break(self, zone_id: int) -> tuple[float | None, float | None]:
        for captured_id, energy in self.zone_energies:
            if captured_id == zone_id:
                return energy, self.median_active_energy
        raise ValueError("Broken zone was not ACTIVE in this snapshot")


class MarketEnergySnapshotCalculator:
    """Capture one shared reference before processing any breaks on a candle.

    Defined ACTIVE-zone energies participate, including zero-energy zones.
    Undefined energies remain in the snapshot but do not enter the median.
    The caller supplies confirmed current history and chooses the zone universe.
    """

    def __init__(self, config: EngineConfig) -> None:
        self._energy = EffectiveZoneEnergyCalculator(config)
        self._time = InteractionTimeDecayCalculator(config)

    def capture(
        self,
        zones: Iterable[Zone],
        current_candle_index: int,
        year_candles: int,
    ) -> MarketEnergySnapshot:
        self._time.calculate(0, 0, current_candle_index, year_candles)
        captured = []
        seen = set()
        for zone in zones:
            if zone.id in seen:
                raise ValueError("Duplicate zone would distort the market reference")
            seen.add(zone.id)
            if zone.state != ZoneState.ACTIVE:
                continue
            captured.append((zone.id, self._energy.calculate(
                zone, current_candle_index, year_candles,
            )))

        values = [energy for _, energy in captured if energy is not None]
        reference = None
        if values:
            # Scale before taking the median to avoid overflow of two large
            # middle values in even-sized populations.
            scale = max(values)
            reference = 0.0 if scale == 0 else median(value / scale for value in values) * scale
        return MarketEnergySnapshot(
            candle_index=current_candle_index,
            zone_energies=tuple(sorted(captured)),
            median_active_energy=reference,
        )
