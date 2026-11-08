"""Diagnostic services for the Eurotherm Smart365 integration."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN
from .modbus import MAX_READ_COUNT, Smart365Error, Smart365ModbusException

SERVICE_READ_REGISTERS = "read_registers"
ATTR_CONFIG_ENTRY_ID = "config_entry_id"
ATTR_ADDRESS = "address"
ATTR_COUNT = "count"
MAX_TOTAL_COUNT = 1000

READ_REGISTERS_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Required(ATTR_ADDRESS): vol.All(vol.Coerce(int), vol.Range(min=0, max=65535)),
        vol.Optional(ATTR_COUNT, default=1): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=MAX_TOTAL_COUNT)
        ),
    }
)


def _loaded_entry(hass: HomeAssistant, entry_id: str | None):
    entries = [
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.state is ConfigEntryState.LOADED
        and (entry_id is None or entry.entry_id == entry_id)
    ]
    if not entries:
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="no_loaded_entry"
        )
    return entries[0]


async def _read_registers(call: ServiceCall) -> ServiceResponse:
    """Read raw holding registers, in blocks of 125 (for exploring the register map).

    Registers that the panel refuses (Modbus exception) are returned as null.
    """
    entry = _loaded_entry(call.hass, call.data.get(ATTR_CONFIG_ENTRY_ID))
    client = entry.runtime_data.client
    start = call.data[ATTR_ADDRESS]
    count = min(call.data[ATTR_COUNT], 65536 - start)
    registers: dict[str, int | None] = {}
    address = start
    while address < start + count:
        block = min(MAX_READ_COUNT, start + count - address)
        try:
            values: list[int | None] = list(await client.read_registers(address, block))
        except Smart365ModbusException:
            values = await _read_one_by_one(client, address, block)
        except Smart365Error as err:
            raise HomeAssistantError(f"Read of register {address} failed: {err}") from err
        for offset, value in enumerate(values):
            registers[str(address + offset)] = value
        address += block
    return {"address": start, "count": count, "registers": registers}


async def _read_one_by_one(client, address: int, count: int) -> list[int | None]:
    """Fallback when a block read fails: read each register on its own."""
    values: list[int | None] = []
    for reg in range(address, address + count):
        try:
            values.append((await client.read_registers(reg, 1))[0])
        except Smart365ModbusException:
            values.append(None)
    return values


def async_setup_services(hass: HomeAssistant) -> None:
    """Register the integration services."""
    hass.services.async_register(
        DOMAIN,
        SERVICE_READ_REGISTERS,
        _read_registers,
        schema=READ_REGISTERS_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
