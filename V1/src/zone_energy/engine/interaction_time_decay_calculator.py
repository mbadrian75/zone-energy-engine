from math import isfinite

from zone_energy.config import EngineConfig
from zone_energy.models import Interaction, InteractionState


class InteractionTimeDecayCalculator:
    """Evaluate current energy using actual candle age without changing history.

    year_candles is supplied for the current market/timeframe; it is not
    inferred from calendar hours or from the interaction's movement time.
    """

    def __init__(self, config: EngineConfig) -> None:
        weight = config.yearly_remaining_weight
        if not isfinite(weight) or not 0 < weight <= 1:
            raise ValueError("yearly_remaining_weight must be finite and in (0, 1]")
        self._yearly_remaining_weight = weight

    def calculate(
        self,
        base_energy: float | None,
        interaction_start_index: int,
        current_candle_index: int,
        year_candles: int,
    ) -> tuple[int, float, float | None]:
        for name, value in (
            ("interaction_start_index", interaction_start_index),
            ("current_candle_index", current_candle_index),
            ("year_candles", year_candles),
        ):
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"{name} must be an integer candle count")
            if value < 0 or (name == "year_candles" and value == 0):
                raise ValueError(f"{name} is outside the valid candle range")
        age = current_candle_index - interaction_start_index
        if age < 0:
            raise ValueError("Current candle cannot precede the interaction origin")
        if base_energy is not None:
            if not isfinite(base_energy) or base_energy < 0:
                raise ValueError("base_energy must be finite and nonnegative")

        weight = self._yearly_remaining_weight ** (age / year_candles)
        current_energy = None if base_energy is None else base_energy * weight
        return age, weight, current_energy

    def evaluate(
        self,
        interaction: Interaction,
        current_candle_index: int,
        year_candles: int,
    ) -> tuple[int, float, float | None]:
        if interaction.state != InteractionState.CLOSED:
            raise ValueError("Finalized energy evaluation requires a CLOSED interaction")
        if interaction.end_index is None or interaction.end_index <= interaction.start_index:
            raise ValueError("Closed interaction requires a valid end index")
        result = self.calculate(
            base_energy=interaction.base_energy,
            interaction_start_index=interaction.start_index,
            current_candle_index=current_candle_index,
            year_candles=year_candles,
        )
        if current_candle_index < interaction.end_index:
            raise ValueError("Finalized energy cannot be evaluated before the move ends")
        return result
