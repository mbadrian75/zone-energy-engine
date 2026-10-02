from zone_energy.config import EngineConfig


class BarrierCalculator:
    """
    Calculates barrier ratio and barrier cost
    at the exact moment of a valid zone break.
    """

    def __init__(
        self,
        config: EngineConfig,
    ) -> None:
        self._config = config

    def calculate(
        self,
        zone_energy: float,
        median_active_energy: float,
    ) -> tuple[float, float]:

        if zone_energy < 0:
            raise ValueError(
                "zone_energy cannot be negative"
            )

        if median_active_energy <= 0:
            raise ValueError(
                "median_active_energy must be greater than zero"
            )

        # V1 explicit rule:
        # a zero-energy broken zone has zero barrier cost.
        if zone_energy == 0:
            return 0.0, 0.0

        barrier_ratio = (
            zone_energy
            / median_active_energy
        )

        barrier_cost = (
            barrier_ratio
            ** self._config.barrier_exponent
        )

        return (
            barrier_ratio,
            barrier_cost,
        )