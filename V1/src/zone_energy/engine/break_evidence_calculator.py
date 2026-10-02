import math


class BreakEvidenceCalculator:
    """
    Calculates displacement evidence and break evidence.

    If persistence is unavailable during bootstrap,
    break evidence is undefined (None).
    """

    @staticmethod
    def calculate(
        barrier_cost: float,
        persistence: float | None,
        displacement_ratio: float,
    ) -> tuple[float, float | None]:

        if barrier_cost < 0:
            raise ValueError(
                "barrier_cost cannot be negative"
            )

        if displacement_ratio < 0:
            raise ValueError(
                "displacement_ratio cannot be negative"
            )

        if persistence is not None and persistence < 0:
            raise ValueError(
                "persistence cannot be negative"
            )

        displacement_evidence = math.log1p(
            displacement_ratio
        )

        # Bootstrap:
        # required previous-move reference is unavailable.
        if persistence is None:
            return (
                displacement_evidence,
                None,
            )

        break_evidence = (
            barrier_cost
            * (
                1.0
                + persistence
                * displacement_evidence
            )
        )

        return (
            displacement_evidence,
            break_evidence,
        )