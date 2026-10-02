from zone_energy.config import EngineConfig
from zone_energy.engine.barrier_calculator import (
    BarrierCalculator,
)
from zone_energy.engine.break_displacement_calculator import (
    BreakDisplacementCalculator,
)
from zone_energy.engine.break_evidence_calculator import (
    BreakEvidenceCalculator,
)
from zone_energy.engine.break_time_calculator import (
    BreakTimeCalculator,
)
from zone_energy.engine.market_energy_snapshot import MarketEnergySnapshot
from zone_energy.models import (
    BreakRecord,
    Candle,
    Interaction,
    Zone,
)


class BreakRecordFactory:
    """
    Creates a BreakRecord from already captured
    zone-energy and median-energy snapshots.

    This factory does not mutate the Zone
    and does not calculate zone energy or median energy.
    """

    def __init__(
        self,
        config: EngineConfig,
    ) -> None:
        self._barrier_calculator = BarrierCalculator(
            config
        )

    def create_from_snapshot(
        self,
        zone: Zone,
        interaction: Interaction,
        break_candle: Candle,
        break_index: int,
        snapshot: MarketEnergySnapshot,
    ) -> BreakRecord:
        """Reuse the same pre-break snapshot for every break on this candle."""
        if break_index != snapshot.candle_index:
            raise ValueError("Break and market snapshot must refer to the same candle")
        zone_energy, median_energy = snapshot.reference_for_break(zone.id)
        return self.create(
            zone=zone,
            interaction=interaction,
            break_candle=break_candle,
            break_index=break_index,
            broken_zone_energy_at_break=zone_energy,
            median_active_zone_energy_at_break=median_energy,
        )

    def create(
        self,
        zone: Zone,
        interaction: Interaction,
        break_candle: Candle,
        break_index: int,
        broken_zone_energy_at_break: float,
        median_active_zone_energy_at_break: float,
    ) -> BreakRecord:

        barrier_ratio, barrier_cost = (
            self._barrier_calculator.calculate(
                zone_energy=broken_zone_energy_at_break,
                median_active_energy=(
                    median_active_zone_energy_at_break
                ),
            )
        )

        (
            break_time_from_origin,
            persistence,
        ) = BreakTimeCalculator.calculate(
            break_index=break_index,
            interaction_start_index=(
                interaction.start_index
            ),
            previous_movement_time=(
                interaction.previous_movement_time
            ),
        )

        (
            displacement,
            displacement_ratio,
        ) = BreakDisplacementCalculator.calculate(
            zone=zone,
            break_candle=break_candle,
        )

        (
            _displacement_evidence,
            break_evidence,
        ) = BreakEvidenceCalculator.calculate(
            barrier_cost=barrier_cost,
            persistence=persistence,
            displacement_ratio=displacement_ratio,
        )

        return BreakRecord(
            broken_zone_id=zone.id,
            break_index=break_index,
            break_close=break_candle.close,
            break_time_from_origin=(
                break_time_from_origin
            ),
            broken_zone_energy_at_break=(
                broken_zone_energy_at_break
            ),
            median_active_zone_energy_at_break=(
                median_active_zone_energy_at_break
            ),
            barrier_ratio=barrier_ratio,
            barrier_cost=barrier_cost,
            displacement=displacement,
            displacement_ratio=displacement_ratio,
            persistence=persistence,
            break_evidence=break_evidence,
        )
