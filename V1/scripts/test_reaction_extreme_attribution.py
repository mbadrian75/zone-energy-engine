"""Regression for candle contact with several zones at one reaction."""
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from zone_energy.engine.return_reversal_detector import ReturnReversalDetector
from zone_energy.engine.role_change_detector import RoleChangeDetector
from zone_energy.models import Candle, PriceSide, Reversal, Zone, ZoneState, ZoneType


def main():
    bars = [Candle(datetime(2025, 1, 3, hour), op, high, low, close, 0)
            for hour, op, high, low, close in
            [(0, 2662, 2663, 2661, 2661.5),
             (1, 2661.5, 2662, 2655.815, 2657),
             (2, 2657, 2662, 2656, 2661)]]
    for mirrored in (False, True):
        reaction_type = ZoneType.RESISTANCE if mirrored else ZoneType.SUPPORT
        opposite = ZoneType.SUPPORT if mirrored else ZoneType.RESISTANCE
        price = lambda value: -value if mirrored else value
        reversal = Reversal(reaction_type, price(2655.815), 29, 30)
        candidates = []
        for zone_id, kind, state, lower, upper, created in [
            (3, opposite, ZoneState.BROKEN, 2657.914, 2660.374, 18),
            (4, reaction_type, ZoneState.ACTIVE, 2653.648, 2655.948, 20),
            (5, reaction_type, ZoneState.ACTIVE, 2656.025, 2660.138, 26),
        ]:
            bounds = sorted((price(lower), price(upper)))
            zone = Zone(id=zone_id, type=kind, state=state,
                        lower_price=bounds[0], upper_price=bounds[1],
                        creation_extreme=bounds[0], creation_index=created,
                        created_at_index=created + 1,
                        last_external_price_side=PriceSide.BELOW if mirrored else PriceSide.ABOVE)
            transformed = [Candle(bar.datetime, -bar.open, -bar.low, -bar.high,
                                  -bar.close, 0) for bar in bars] if mirrored else bars
            detector = RoleChangeDetector if state == ZoneState.BROKEN else ReturnReversalDetector
            if detector.detect(zone, reversal, *transformed):
                candidates.append(zone_id)
            # Both boundary prices belong to the zone, including role changes.
            for boundary in bounds:
                edge = Reversal(reaction_type, boundary, 29, 30)
                assert detector.detect(zone, edge, *transformed)
        assert candidates == [4], candidates
    print("Extreme attribution and inclusive boundaries: PASS")


if __name__ == "__main__":
    main()
