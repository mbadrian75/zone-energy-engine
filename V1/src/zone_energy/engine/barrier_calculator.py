from zone_energy.config import EngineConfig
from math import isfinite, log10, log, log1p, exp


class EnergyOverflowError(ValueError):
    """The configured formula exceeds the finite numeric representation."""


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
        if config.barrier_cost_transform not in ("power","log1p"):
            raise ValueError("Unsupported barrier cost transform")

    def calculate(
        self,
        zone_energy: float,
        median_active_energy: float,
    ) -> tuple[float, float]:

        if not isfinite(zone_energy) or zone_energy < 0:
            raise ValueError(
                "zone_energy cannot be negative"
            )

        if not isfinite(median_active_energy) or median_active_energy <= 0:
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

        exponent = self._config.barrier_exponent
        if not isfinite(exponent) or exponent <= 0:
            raise ValueError("barrier_exponent must be finite and positive")
        # log(1 + ratio**exponent), evaluated without constructing the power.
        # For exponent=2 this is the user-approved logarithmic barrier model.
        log_power = exponent * (log(zone_energy)-log(median_active_energy))
        barrier_cost = (log_power + log1p(exp(-log_power)) if log_power > 0
                        else log1p(exp(log_power)))
        if self._config.barrier_cost_transform == "power":
            try:
                barrier_cost = barrier_ratio ** exponent
            except OverflowError:
                barrier_cost = float("inf")
        if not isfinite(barrier_ratio) or not isfinite(barrier_cost):
            magnitude = exponent * (log10(zone_energy)-log10(median_active_energy))
            raise EnergyOverflowError(
                f"Barrier overflow: zone_energy={zone_energy!r}, median_active_energy={median_active_energy!r}, "
                f"barrier_ratio={barrier_ratio!r}, exponent={exponent!r}, log10_power={magnitude!r}")

        return (
            barrier_ratio,
            barrier_cost,
        )
