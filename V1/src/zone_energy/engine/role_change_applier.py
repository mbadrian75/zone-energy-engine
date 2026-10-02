from zone_energy.models import (
    Zone,
    ZoneState,
    ZoneType,
)


class RoleChangeApplier:
    """
    Applies a confirmed role change to a zone.

    Zone boundaries remain unchanged.
    """

    @staticmethod
    def apply(zone: Zone) -> None:
        if zone.state != ZoneState.BROKEN:
            raise ValueError(
                f"Role change can only be applied "
                f"to a BROKEN zone. "
                f"Zone {zone.id} is {zone.state}."
            )

        if zone.type == ZoneType.SUPPORT:
            zone.type = ZoneType.RESISTANCE
            zone.state = ZoneState.ACTIVE
            return

        if zone.type == ZoneType.RESISTANCE:
            zone.type = ZoneType.SUPPORT
            zone.state = ZoneState.ACTIVE
            return

        raise ValueError(
            f"Unsupported zone type: {zone.type}"
        )