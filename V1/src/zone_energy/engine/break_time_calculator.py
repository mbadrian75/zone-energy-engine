class BreakTimeCalculator:
    """
    Calculates break time from interaction origin
    and persistence relative to the previous move.

    In bootstrap mode, when previous_movement_time
    does not exist, persistence is undefined (None).
    """

    @staticmethod
    def calculate(
        break_index: int,
        interaction_start_index: int,
        previous_movement_time: int | None,
    ) -> tuple[int, float | None]:

        break_time_from_origin = (
            break_index - interaction_start_index
        )

        if break_time_from_origin < 0:
            raise ValueError(
                "break_index cannot be earlier than "
                "interaction_start_index"
            )

        # Bootstrap:
        # no previous move exists yet.
        if previous_movement_time is None:
            return (
                break_time_from_origin,
                None,
            )

        if previous_movement_time <= 0:
            raise ValueError(
                "previous_movement_time must be "
                "greater than zero"
            )

        persistence = (
            break_time_from_origin
            / previous_movement_time
        )

        return (
            break_time_from_origin,
            persistence,
        )