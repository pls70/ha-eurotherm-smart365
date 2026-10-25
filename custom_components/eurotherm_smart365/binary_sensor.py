"""Binary sensors for the Eurotherm Smart365 integration."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    ERR_BATTERY,
    ERR_CONDENSATION,
    ERR_SENSOR_FAULT,
    ROOM_SENSOR_ERRORS,
    SENSOR_TYPE_TEMP_HUMIDITY,
)
from .coordinator import Room, Smart365ConfigEntry, Smart365Coordinator
from .entity import Smart365RoomEntity


@dataclass(frozen=True, kw_only=True)
class RoomErrorDescription(BinarySensorEntityDescription):
    """Describes a binary sensor built from the room error bit mask."""

    mask: int
    needs_humidity: bool = False


ROOM_ERRORS = (
    RoomErrorDescription(
        key="battery",
        device_class=BinarySensorDeviceClass.BATTERY,
        entity_category=EntityCategory.DIAGNOSTIC,
        mask=ERR_BATTERY,
    ),
    RoomErrorDescription(
        key="sensor_fault",
        translation_key="sensor_fault",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        mask=ERR_SENSOR_FAULT,
    ),
    RoomErrorDescription(
        key="condensation",
        translation_key="condensation",
        device_class=BinarySensorDeviceClass.MOISTURE,
        mask=ERR_CONDENSATION,
        needs_humidity=True,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: Smart365ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up binary sensors."""
    coordinator = entry.runtime_data
    async_add_entities(
        RoomErrorSensor(coordinator, room, description)
        for room in coordinator.topology.rooms
        for description in ROOM_ERRORS
        if room.sensor_type == SENSOR_TYPE_TEMP_HUMIDITY or not description.needs_humidity
    )


class RoomErrorSensor(Smart365RoomEntity, BinarySensorEntity):
    """A flag from the room sensor error mask."""

    entity_description: RoomErrorDescription

    def __init__(
        self, coordinator: Smart365Coordinator, room: Room, description: RoomErrorDescription
    ) -> None:
        super().__init__(coordinator, room, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool:
        return bool(self.room_regs[ROOM_SENSOR_ERRORS] & self.entity_description.mask)
