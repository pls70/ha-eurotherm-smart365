"""Temperature levels of the Home Assistant weekly program."""

from __future__ import annotations

from homeassistant.components.number import NumberDeviceClass, NumberMode, RestoreNumber
from homeassistant.const import EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import Smart365ConfigEntry, Smart365Coordinator
from .entity import Smart365ZoneEntity
from .program import LEVELS, ZoneProgram


async def async_setup_entry(
    hass: HomeAssistant,
    entry: Smart365ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the program level temperatures of each zone."""
    coordinator = entry.runtime_data
    async_add_entities(
        ProgramLevelNumber(coordinator, program, level)
        for program in coordinator.programs.values()
        for level in LEVELS
    )


class ProgramLevelNumber(Smart365ZoneEntity, RestoreNumber):
    """Temperature of one level of the zone's Home Assistant program.

    Stored in Home Assistant: the panel's own level temperatures are not
    reachable over Modbus.
    """

    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_native_min_value = 5
    _attr_native_max_value = 30
    _attr_native_step = 0.5
    _attr_mode = NumberMode.BOX
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: Smart365Coordinator, program: ZoneProgram, level: int) -> None:
        super().__init__(coordinator, program.zone, f"program_level{level}")
        self._program = program
        self._level = level
        self._attr_translation_key = f"program_level{level}"

    @property
    def available(self) -> bool:
        return True

    @property
    def native_value(self) -> float:
        return self._program.temps[self._level]

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_number_data()) and last.native_value is not None:
            self._program.temps[self._level] = float(last.native_value)

    async def async_set_native_value(self, value: float) -> None:
        await self._program.async_set_temperature(self._level, value)
        self.async_write_ha_state()
