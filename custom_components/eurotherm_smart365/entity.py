"""Base entities for the Eurotherm Smart365 integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, MODEL
from .coordinator import Room, Smart365Coordinator


class Smart365Entity(CoordinatorEntity[Smart365Coordinator]):
    """Entity attached to the SmartComfort 365 panel."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: Smart365Coordinator, key: str) -> None:
        super().__init__(coordinator)
        self._entry_id = coordinator.config_entry.unique_id or coordinator.config_entry.entry_id
        self._attr_unique_id = f"{self._entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._entry_id)},
            manufacturer=MANUFACTURER,
            model=MODEL,
            name=MODEL,
            serial_number=coordinator.config_entry.unique_id,
        )


class Smart365ZoneEntity(Smart365Entity):
    """Entity attached to a zone."""

    def __init__(self, coordinator: Smart365Coordinator, zone: int, key: str) -> None:
        super().__init__(coordinator, f"zone{zone}_{key}")
        self.zone = zone
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{self._entry_id}_zone{zone}")},
            manufacturer=MANUFACTURER,
            model="Zona",
            name=f"Zona {zone + 1}",
            via_device=(DOMAIN, self._entry_id),
        )

    @property
    def zone_regs(self) -> list[int] | None:
        """Raw registers of this zone."""
        return self.coordinator.data.zones.get(self.zone)

    @property
    def available(self) -> bool:
        return super().available and self.zone_regs is not None


class Smart365RoomEntity(Smart365Entity):
    """Entity attached to a room."""

    def __init__(self, coordinator: Smart365Coordinator, room: Room, key: str) -> None:
        super().__init__(coordinator, f"room{room.key}_{key}")
        self.room = room
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{self._entry_id}_room{room.key}")},
            manufacturer=MANUFACTURER,
            model="Stanza",
            name=f"Stanza {room.number}",
            via_device=(
                (DOMAIN, f"{self._entry_id}_zone{room.zone}")
                if room.zone in coordinator.topology.zones
                else (DOMAIN, self._entry_id)
            ),
        )

    @property
    def room_regs(self) -> list[int] | None:
        """Raw registers of this room."""
        return self.coordinator.data.rooms.get(self.room.key)

    @property
    def zone_regs(self) -> list[int] | None:
        """Raw registers of the zone this room belongs to."""
        return self.coordinator.data.zones.get(self.room.zone)

    @property
    def available(self) -> bool:
        return super().available and self.room_regs is not None
