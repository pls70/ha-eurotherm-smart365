"""Room thermostats for the Eurotherm Smart365 integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.climate import (
    ATTR_HVAC_MODE,
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    OPERATIVE_COOLING,
    ROOM_HUMIDITY,
    ROOM_MANUAL_TEMP,
    ROOM_MODE,
    ROOM_MODE_AUTO,
    ROOM_MODE_MANUAL,
    ROOM_MODE_NAMES,
    ROOM_MODE_OFF,
    ROOM_TARGET_TEMP,
    ROOM_TEMP,
    SENSOR_TYPE_TEMP_HUMIDITY,
    ZONE_MODE,
    ZONE_MODE_OFF,
    ZONE_OPERATIVE_MODE,
    from_temperature,
    room_address,
    to_temperature,
)
from .coordinator import Room, Smart365ConfigEntry, Smart365Coordinator
from .entity import Smart365RoomEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: Smart365ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up a thermostat for each room."""
    coordinator = entry.runtime_data
    async_add_entities(Smart365Climate(coordinator, room) for room in coordinator.topology.rooms)


class Smart365Climate(Smart365RoomEntity, ClimateEntity):
    """A room thermostat.

    AUTO follows the panel's weekly program; HEAT/COOL (depending on the
    season set on the zone) is the panel's manual mode. Rooms cannot be
    switched off one by one: the whole zone is turned off from its select.
    """

    _attr_name = None
    _attr_translation_key = "room"
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = 0.5
    _attr_min_temp = 5
    _attr_max_temp = 35
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE

    def __init__(self, coordinator: Smart365Coordinator, room: Room) -> None:
        super().__init__(coordinator, room, "climate")

    @property
    def _manual_hvac_mode(self) -> HVACMode:
        zone = self.zone_regs
        if zone is not None and zone[ZONE_OPERATIVE_MODE] == OPERATIVE_COOLING:
            return HVACMode.COOL
        return HVACMode.HEAT

    @property
    def current_temperature(self) -> float | None:
        return to_temperature(self.room_regs[ROOM_TEMP])

    @property
    def current_humidity(self) -> float | None:
        if self.room.sensor_type != SENSOR_TYPE_TEMP_HUMIDITY:
            return None
        return self.room_regs[ROOM_HUMIDITY]

    @property
    def target_temperature(self) -> float | None:
        return to_temperature(self.room_regs[ROOM_TARGET_TEMP])

    @property
    def hvac_mode(self) -> HVACMode:
        mode = self.room_regs[ROOM_MODE]
        zone = self.zone_regs
        if mode == ROOM_MODE_OFF or (zone is not None and zone[ZONE_MODE] == ZONE_MODE_OFF):
            return HVACMode.OFF
        if mode == ROOM_MODE_AUTO:
            return HVACMode.AUTO
        return self._manual_hvac_mode

    @property
    def hvac_modes(self) -> list[HVACMode]:
        modes = [HVACMode.AUTO, self._manual_hvac_mode]
        if self.hvac_mode == HVACMode.OFF:
            modes.append(HVACMode.OFF)
        return modes

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        mode = self.room_regs[ROOM_MODE]
        return {
            "room_mode": ROOM_MODE_NAMES.get(mode, str(mode)),
            "module": self.room.module + 1,
            "room_index": self.room.index + 1,
        }

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set a manual temperature, switching the room to manual mode."""
        if (hvac_mode := kwargs.get(ATTR_HVAC_MODE)) == HVACMode.AUTO:
            await self.async_set_hvac_mode(hvac_mode)
            return
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is None:
            return
        await self._async_set_manual(temperature)

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Switch between the weekly program and manual mode."""
        if hvac_mode == HVACMode.AUTO:
            await self.coordinator.async_write(
                room_address(self.room.module, self.room.index, ROOM_MODE), ROOM_MODE_AUTO
            )
        elif hvac_mode in (HVACMode.HEAT, HVACMode.COOL):
            await self._async_set_manual(self.target_temperature)

    async def _async_set_manual(self, temperature: float | None) -> None:
        if temperature is not None:
            await self.coordinator.client_write(
                room_address(self.room.module, self.room.index, ROOM_MANUAL_TEMP),
                from_temperature(temperature),
            )
        await self.coordinator.async_write(
            room_address(self.room.module, self.room.index, ROOM_MODE), ROOM_MODE_MANUAL
        )
