"""Write/read one isolated checkpoint in market_data, then remove that test record."""

import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pymongo import MongoClient
from zone_energy.config import EngineConfig
from zone_energy.data import EngineResultsRepository
from zone_energy.models import Interaction, InteractionState, Zone, ZoneState, ZoneType


def main():
    client = MongoClient("mongodb://localhost:27017/", serverSelectionTimeoutMS=5000)
    repository = EngineResultsRepository(client=client)
    run_id = "integration-test-" + uuid4().hex
    checkpoint_id = None
    try:
        client.admin.command("ping")
        zone = Zone(1, ZoneType.SUPPORT, ZoneState.ACTIVE, 99, 101, 100, 0,
                    created_at_index=1,
                    interactions=[Interaction(1, 1, InteractionState.CLOSED, 100, 0,
                                              end_index=10, base_energy=10)])
        options = dict(run_id=run_id, symbol="TEST", current_candle_index=1000,
                       year_candles=1000, config=EngineConfig())
        checkpoint_id = repository.save_checkpoint([zone], **options)
        assert repository.load_zones(checkpoint_id) == [zone]
        assert repository.get_checkpoint(checkpoint_id)["effective_zone_energies"] == [
            {"zone_id": 1, "energy": 0.5}]
        assert repository.save_checkpoint([zone], **options) == checkpoint_id
        print("Checkpoint write/read and repeat-save in market_data: PASS")
    finally:
        # Delete only this test's unique record, including after a failed assertion.
        client["market_data"][EngineResultsRepository.COLLECTION].delete_one({"run_id": run_id})
        client.close()


if __name__ == "__main__":
    main()
