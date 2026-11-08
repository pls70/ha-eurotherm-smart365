"""Config flow for the Eurotherm Smart365 integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigEntryState,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback
from homeassistant.helpers.selector import EntitySelector, EntitySelectorConfig

from .const import CONF_UNIT_ID, DEFAULT_PORT, DEFAULT_UNIT_ID, DOMAIN, MODEL, REG_SERIAL_HIGH
from .modbus import Smart365Client, Smart365Error
from .program import CONF_CLIMATES, CONF_LEVEL2_SCHEDULE, CONF_LEVEL3_SCHEDULE

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): vol.All(int, vol.Range(min=1, max=65535)),
        vol.Required(CONF_UNIT_ID, default=DEFAULT_UNIT_ID): vol.All(int, vol.Range(min=0, max=247)),
    }
)


async def _read_serial(host: str, port: int, unit_id: int) -> str:
    """Connect to the device and return its serial number."""
    client = Smart365Client(host, port, unit_id)
    try:
        high, low = await client.read_registers(REG_SERIAL_HIGH, 2)
    finally:
        await client.close()
    return str((high << 16) | low)


class Smart365ConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Eurotherm Smart365."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Options: schedules of the Home Assistant weekly program."""
        return Smart365OptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask for the panel address."""
        errors: dict[str, str] = {}
        if user_input is not None:
            self._async_abort_entries_match({CONF_HOST: user_input[CONF_HOST]})
            try:
                serial = await _read_serial(
                    user_input[CONF_HOST], user_input[CONF_PORT], user_input[CONF_UNIT_ID]
                )
            except Smart365Error:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(serial)
                self._abort_if_unique_id_configured(updates={CONF_HOST: user_input[CONF_HOST]})
                return self.async_create_entry(title=MODEL, data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(STEP_USER_SCHEMA, user_input),
            errors=errors,
        )


class Smart365OptionsFlow(OptionsFlow):
    """Link Home Assistant schedule helpers to each zone's program levels."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        entry = self.config_entry
        zones = [0]
        if entry.state is ConfigEntryState.LOADED:
            zones = entry.runtime_data.topology.zones or zones
        selector = EntitySelector(EntitySelectorConfig(domain="schedule"))
        climates = EntitySelector(EntitySelectorConfig(domain="climate", multiple=True))
        fields: dict = {}
        for zone in zones:
            for key in (CONF_LEVEL2_SCHEDULE, CONF_LEVEL3_SCHEDULE):
                fields[vol.Optional(key.format(zone=zone))] = selector
            fields[vol.Optional(CONF_CLIMATES.format(zone=zone))] = climates
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(vol.Schema(fields), entry.options),
        )
