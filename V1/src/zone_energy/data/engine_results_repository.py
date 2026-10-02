from collections.abc import Iterable
from dataclasses import asdict
from enum import Enum
import json
from math import isfinite

from zone_energy.config import EngineConfig
from zone_energy.engine.effective_zone_energy_calculator import EffectiveZoneEnergyCalculator
from zone_energy.models import BreakRecord, Interaction, InteractionState, PriceSide, Zone, ZoneState, ZoneType


def _plain(value):
    """Convert model fields into finite BSON-compatible values."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, float) and not isfinite(value):
        raise ValueError("Checkpoint cannot contain NaN or infinity")
    if isinstance(value, int) and not -(2 ** 63) <= value < 2 ** 63:
        raise ValueError("Checkpoint integer exceeds BSON int64 range")
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _decode_zone(document):
    values = dict(document)
    values["type"] = ZoneType(values["type"])
    values["state"] = ZoneState(values["state"])
    if values["last_external_price_side"] is not None:
        values["last_external_price_side"] = PriceSide(values["last_external_price_side"])
    interactions = []
    for saved in values["interactions"]:
        move = dict(saved)
        move["state"] = InteractionState(move["state"])
        move["breaks"] = [BreakRecord(**record) for record in move["breaks"]]
        interactions.append(Interaction(**move))
    values["interactions"] = interactions
    return Zone(**values)


class EngineResultsRepository:
    """Persist complete immutable checkpoints in the candle database.

    One MongoDB document holds a checkpoint, so a partial multi-collection
    save cannot occur. Candle collections are never accessed by this class.
    run_id must uniquely identify a replay or live processing sequence.
    """

    COLLECTION = "zone_energy_checkpoints"
    SCHEMA_VERSION = 1

    def __init__(self, mongo_uri="mongodb://localhost:27017/",
                 database_name="market_data", *, client=None):
        self._owns_client = client is None
        if client is None:
            from pymongo import MongoClient
            client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
        self._client = client
        self._collection = client[database_name][self.COLLECTION]

    def close(self):
        if self._owns_client:
            self._client.close()

    def save_checkpoint(
        self,
        zones: Iterable[Zone],
        *,
        run_id: str,
        symbol: str,
        current_candle_index: int,
        year_candles: int,
        config: EngineConfig,
        replay_context: dict | None = None,
    ) -> str:
        for name, value in (("run_id", run_id), ("symbol", symbol)):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a nonempty string")
        from zone_energy.engine.interaction_time_decay_calculator import InteractionTimeDecayCalculator
        InteractionTimeDecayCalculator(config).calculate(0, 0, current_candle_index, year_candles)
        history = list(zones)
        if len({zone.id for zone in history}) != len(history):
            raise ValueError("Checkpoint contains duplicate zone IDs")
        move_ids = [move.id for zone in history for move in zone.interactions]
        if len(set(move_ids)) != len(move_ids):
            raise ValueError("Checkpoint contains duplicate interaction IDs")
        energy = EffectiveZoneEnergyCalculator(config)
        effective = []
        for zone in history:
            if any(record.break_index > current_candle_index
                   for move in zone.interactions for record in move.breaks):
                raise ValueError("Checkpoint contains future break evidence")
            effective.append({"zone_id": zone.id, "energy": energy.calculate(
                zone, current_candle_index, year_candles,
            )})
        identifier = json.dumps([run_id, symbol, config.timeframe.value, current_candle_index],
                                ensure_ascii=True, separators=(",", ":"))
        document = _plain({
            "_id": identifier, "schema_version": self.SCHEMA_VERSION,
            "run_id": run_id, "symbol": symbol, "timeframe": config.timeframe,
            "current_candle_index": current_candle_index, "year_candles": year_candles,
            "config": asdict(config), "zones": [asdict(zone) for zone in sorted(history, key=lambda item: item.id)],
            "effective_zone_energies": sorted(effective, key=lambda item: item["zone_id"]),
        })
        if replay_context is not None:
            document["replay_context"] = _plain(replay_context)
        # Insert once; retrying identical data is safe and cannot replace history.
        self._collection.update_one({"_id": identifier}, {"$setOnInsert": document}, upsert=True)
        stored = self._collection.find_one({"_id": identifier})
        if stored != document:
            raise ValueError("Checkpoint already exists with different data; use a distinct run_id")
        return identifier

    def get_checkpoint(self, checkpoint_id: str) -> dict | None:
        document = self._collection.find_one({"_id": checkpoint_id})
        if document is not None and document.get("schema_version") != self.SCHEMA_VERSION:
            raise ValueError("Unsupported checkpoint schema version")
        return document

    def load_zones(self, checkpoint_id: str) -> list[Zone] | None:
        document = self.get_checkpoint(checkpoint_id)
        if document is None:
            return None
        return [_decode_zone(zone) for zone in document["zones"]]
