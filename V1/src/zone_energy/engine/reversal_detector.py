from zone_energy.models import (
    Candle,
    Reversal,
    ZoneType,
)


class ReversalDetector:
    """
    Detects confirmed three-candle reversals.
    """

    @staticmethod
    def detect(
        c1: Candle,
        c2: Candle,
        c3: Candle,
        c1_index: int,
        c2_index: int,
        c3_index: int,
        *,
        previous_type: ZoneType | None = None,
    ) -> Reversal | None:

        is_resistance = (
            c2.high > c1.high
            and c2.high > c3.high
        )

        is_support = (
            c2.low < c1.low
            and c2.low < c3.low
        )

        # A dual extreme alternates from the previous confirmed reaction.
        if is_resistance and is_support:
            if previous_type is None:
                return None
            if previous_type == ZoneType.RESISTANCE:
                is_resistance = False
            elif previous_type == ZoneType.SUPPORT:
                is_support = False
            else:
                raise ValueError("Unsupported previous reaction type")

        if is_resistance:
            return Reversal(
                type=ZoneType.RESISTANCE,
                extreme_price=c2.high,
                extreme_index=c2_index,
                detection_index=c3_index,
            )

        if is_support:
            return Reversal(
                type=ZoneType.SUPPORT,
                extreme_price=c2.low,
                extreme_index=c2_index,
                detection_index=c3_index,
            )

        return None
