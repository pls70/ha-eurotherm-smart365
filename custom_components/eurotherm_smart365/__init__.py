"""The Eurotherm Smart365 integration."""

from __future__ import annotations

from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import CONF_UNIT_ID, DOMAIN, MANUFACTURER, MODEL
from .coordinator import Smart365ConfigEntry, Smart365Coordinator
from .modbus import Smart365Client

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.CLIMATE,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def async_setup_entry(hass: HomeAssistant, entry: Smart365ConfigEntry) -> bool:
    """Set up Eurotherm Smart365 from a config entry."""
    client = Smart365Client(entry.data[CONF_HOST], entry.data[CONF_PORT], entry.data[CONF_UNIT_ID])
    coordinator = Smart365Coordinator(hass, entry, client)
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception:
        await client.close()
        raise
    entry.runtime_data = coordinator

    # Register the panel and zone devices first: rooms are linked to them.
    device_registry = dr.async_get(hass)
    panel_id = entry.unique_id or entry.entry_id
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, panel_id)},
        manufacturer=MANUFACTURER,
        model=MODEL,
        name=MODEL,
        serial_number=entry.unique_id,
    )
    for zone in coordinator.topology.zones:
        device_registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, f"{panel_id}_zone{zone}")},
            manufacturer=MANUFACTURER,
            model="Zona",
            name=f"Zona {zone + 1}",
            via_device=(DOMAIN, panel_id),
        )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: Smart365ConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.client.close()
    return unloaded
