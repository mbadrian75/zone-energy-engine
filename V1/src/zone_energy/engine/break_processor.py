from collections.abc import Iterable
from dataclasses import fields
from math import isfinite

from zone_energy.config import EngineConfig
from zone_energy.engine.break_detector import BreakDetector
from zone_energy.engine.break_record_factory import BreakRecordFactory
from zone_energy.engine.market_energy_snapshot import MarketEnergySnapshotCalculator
from zone_energy.models import BreakRecord, Candle, Interaction, InteractionState, Zone, ZoneState


class BreakProcessor:
    """Process one closed candle's breaks for a supplied origin interaction.

    The caller selects the origin and supplies confirmed market history.
    All records are built against one pre-break snapshot before any mutation.
    This processor changes state, but never changes zone type or base energy.
    """

    def __init__(self, config: EngineConfig) -> None:
        self._snapshots = MarketEnergySnapshotCalculator(config)
        self._records = BreakRecordFactory(config)

    def process(
        self,
        interaction: Interaction,
        origin_zone: Zone,
        zones: Iterable[Zone],
        candle: Candle,
        candle_index: int,
        year_candles: int,
    ) -> list[BreakRecord]:
        if interaction.state != InteractionState.OPEN or interaction.base_energy is not None:
            raise ValueError("Break evidence requires an unfinalized OPEN interaction")
        if interaction.zone_id != origin_zone.id:
            raise ValueError("Interaction does not belong to origin_zone")
        if interaction.start_index < origin_zone.creation_index:
            raise ValueError("Interaction starts before origin_zone exists")
        if interaction.start_index > candle_index:
            raise ValueError("Break candle precedes interaction origin")
        if not all(isfinite(value) for value in (candle.open, candle.high, candle.low, candle.close)):
            raise ValueError("Break candle prices must be finite")
        history = list(zones)
        if not any(zone is origin_zone for zone in history):
            raise ValueError("Market history must include the supplied origin_zone")
        snapshot = self._snapshots.capture(history, candle_index, year_candles)
        targets = sorted(
            (zone for zone in history
             if zone.id != origin_zone.id and BreakDetector.is_broken(zone, candle)),
            key=lambda zone: zone.id,
        )
        if any(record.break_index > candle_index for record in interaction.breaks):
            raise ValueError("Break candles must be processed chronologically")
        if not targets:
            return []
        if any(record.break_index == candle_index for record in interaction.breaks):
            raise ValueError("All breaks on a candle must be processed in one batch")

        records = []
        for zone in targets:
            record = self._records.create_from_snapshot(
                zone, interaction, candle, candle_index, snapshot,
            )
            for field in fields(record):
                value = getattr(record, field.name)
                if value is not None and not isfinite(value):
                    raise ValueError("Break record contains a nonfinite measurement")
            records.append(record)

        # Commit mutations only after every candidate record has succeeded.
        interaction.breaks.extend(records)
        for zone in targets:
            zone.state = ZoneState.BROKEN
        return records
