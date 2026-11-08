"""Zone switches for the Eurotherm Smart365 integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import ZONE_AIR_BOOST, zone_address
from .coordinator import Smart365ConfigEntry, Smart365Coordinator
from .entity import Smart365ZoneEntity
from .program import ZoneProgram


async def async_setup_entry(
    hass: HomeAssistant,
    entry: Smart365ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up zone switches."""
    coordinator = entry.runtime_data
    entities: list[SwitchEntity] = [
        AirBoostSwitch(coordinator, zone) for zone in coordinator.topology.zones
    ]
    entities.extend(ProgramSwitch(coordinator, p) for p in coordinator.programs.values())
    async_add_entities(entities)


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


class ProgramSwitch(Smart365ZoneEntity, SwitchEntity, RestoreEntity):
    """Run the zone's weekly program from Home Assistant instead of the panel.

    On: rooms follow the Home Assistant schedules (in manual mode on the panel).
    Off: rooms go back to the panel's own program.
    """

    _attr_translation_key = "ha_program"

    def __init__(self, coordinator: Smart365Coordinator, program: ZoneProgram) -> None:
        super().__init__(coordinator, program.zone, "ha_program")
        self._program = program

    @property
    def available(self) -> bool:
        return True

    @property
    def is_on(self) -> bool:
        return self._program.enabled

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "level": self._program.level,
            "target_temperature": self._program.target,
            "level2_schedule": self._program.schedules[2],
            "level3_schedule": self._program.schedules[3],
        }

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_state()) is not None:
            self._program.enabled = last.state == STATE_ON
        self.async_on_remove(self._program.async_add_listener(self.async_write_ha_state))

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._program.async_set_enabled(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._program.async_set_enabled(False)
