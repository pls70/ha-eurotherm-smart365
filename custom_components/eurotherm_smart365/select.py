"""Zone selects for the Eurotherm Smart365 integration."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    DOMAIN,
    OPERATIVE_COOLING,
    OPERATIVE_HEATING,
    ZONE_MODE,
    ZONE_MODE_AWAY,
    ZONE_MODE_HOLIDAY,
    ZONE_MODE_HOME,
    ZONE_MODE_OFF,
    ZONE_OPERATIVE_MODE,
    zone_address,
)
from .coordinator import Smart365ConfigEntry, Smart365Coordinator
from .entity import Smart365ZoneEntity

ZONE_MODES = {
    ZONE_MODE_HOME: "home",
    ZONE_MODE_OFF: "off",
    ZONE_MODE_AWAY: "away",
    ZONE_MODE_HOLIDAY: "holiday",
}
SEASONS = {OPERATIVE_COOLING: "cooling", OPERATIVE_HEATING: "heating"}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: Smart365ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up zone selects."""
    coordinator = entry.runtime_data
    entities: list[SelectEntity] = []
    for zone in coordinator.topology.zones:
        entities.append(ZoneRegisterSelect(coordinator, zone, "zone_mode", ZONE_MODE, ZONE_MODES))
        entities.append(
            ZoneRegisterSelect(coordinator, zone, "season", ZONE_OPERATIVE_MODE, SEASONS)
        )
    async_add_entities(entities)


class ZoneRegisterSelect(Smart365ZoneEntity, SelectEntity):
    """A zone register with a fixed set of values."""

    def __init__(
        self,
        coordinator: Smart365Coordinator,
        zone: int,
        key: str,
        field: int,
        values: dict[int, str],
    ) -> None:
        super().__init__(coordinator, zone, key)
        self._field = field
        self._values = values
        self._attr_translation_key = key
        self._attr_options = list(values.values())

    @property
    def current_option(self) -> str | None:
        return self._values.get(self.zone_regs[self._field])

    async def async_select_option(self, option: str) -> None:
        if option == "holiday":
            # Holiday mode is read-only over Modbus: it is set from the panel or app.
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="holiday_read_only"
            )
        value = next(raw for raw, name in self._values.items() if name == option)
        await self.coordinator.async_write(zone_address(self.zone, self._field), value)
