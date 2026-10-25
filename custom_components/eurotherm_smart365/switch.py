"""Zone switches for the Eurotherm Smart365 integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import ZONE_AIR_BOOST, zone_address
from .coordinator import Smart365ConfigEntry, Smart365Coordinator
from .entity import Smart365ZoneEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: Smart365ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up zone switches."""
    coordinator = entry.runtime_data
    async_add_entities(AirBoostSwitch(coordinator, zone) for zone in coordinator.topology.zones)


class AirBoostSwitch(Smart365ZoneEntity, SwitchEntity):
    """Air renewal boost, only useful when air units are installed."""

    _attr_translation_key = "air_boost"
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: Smart365Coordinator, zone: int) -> None:
        super().__init__(coordinator, zone, "air_boost")

    @property
    def is_on(self) -> bool:
        return self.zone_regs[ZONE_AIR_BOOST] == 1

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_write(zone_address(self.zone, ZONE_AIR_BOOST), 1)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_write(zone_address(self.zone, ZONE_AIR_BOOST), 0)
