"""Data coordinator for the Eurotherm Smart365 integration."""

from __future__ import annotations

from dataclasses import dataclass, field
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_MODULES,
    MODULE_BLOCK_LEN,
    MODULE_NUM_SENSORS,
    REG_NUM_ZONES,
    REG_OUTDOOR_TEMP,
    ROOM_BLOCK_LEN,
    ROOM_SENSOR_TYPE,
    ROOM_ZONE_ID,
    ROOMS_PER_MODULE,
    ZONE_BLOCK_LEN,
    ZONE_MODULE_BITMAP,
    module_address,
    room_address,
    zone_address,
)
from .modbus import Smart365Client, Smart365Error, Smart365ModbusException

_LOGGER = logging.getLogger(__name__)

type Smart365ConfigEntry = ConfigEntry[Smart365Coordinator]


@dataclass(frozen=True)
class Room:
    """A room discovered on the system."""

    module: int
    index: int
    zone: int
    sensor_type: int

    @property
    def key(self) -> str:
        """Stable identifier of the room."""
        return f"{self.module}_{self.index}"

    @property
    def number(self) -> int:
        """1-based room number across all modules."""
        return self.module * ROOMS_PER_MODULE + self.index + 1


@dataclass
class Topology:
    """Zones, modules and rooms present on the system."""

    zones: list[int] = field(default_factory=list)
    modules: list[int] = field(default_factory=list)
    rooms: list[Room] = field(default_factory=list)


@dataclass
class Smart365Data:
    """A snapshot of all polled registers."""

    outdoor_temp_raw: int | None = None
    zones: dict[int, list[int]] = field(default_factory=dict)
    modules: dict[int, list[int]] = field(default_factory=dict)
    rooms: dict[str, list[int]] = field(default_factory=dict)


class Smart365Coordinator(DataUpdateCoordinator[Smart365Data]):
    """Polls the SmartComfort 365 over Modbus TCP."""

    config_entry: Smart365ConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: Smart365ConfigEntry, client: Smart365Client
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=DEFAULT_SCAN_INTERVAL,
        )
        self.client = client
        self.topology = Topology()

    async def _async_setup(self) -> None:
        try:
            self.topology = await discover(self.client)
        except Smart365Error as err:
            raise UpdateFailed(f"Discovery failed: {err}") from err
        _LOGGER.debug("Discovered topology: %s", self.topology)

    async def _async_update_data(self) -> Smart365Data:
        client = self.client
        data = Smart365Data()
        try:
            data.outdoor_temp_raw = (await client.read_registers(REG_OUTDOOR_TEMP, 1))[0]
            for zone in self.topology.zones:
                data.zones[zone] = await client.read_registers(
                    zone_address(zone), ZONE_BLOCK_LEN
                )
            for module in self.topology.modules:
                data.modules[module] = await client.read_registers(
                    module_address(module), MODULE_BLOCK_LEN
                )
            for room in self.topology.rooms:
                data.rooms[room.key] = await client.read_registers(
                    room_address(room.module, room.index), ROOM_BLOCK_LEN
                )
        except Smart365Error as err:
            raise UpdateFailed(str(err)) from err
        return data

    async def client_write(self, address: int, value: int) -> None:
        """Write a register without refreshing."""
        try:
            await self.client.write_register(address, value)
        except Smart365Error as err:
            raise HomeAssistantError(f"Write to register {address} failed: {err}") from err

    async def async_write(self, address: int, value: int) -> None:
        """Write a register and refresh the data."""
        await self.client_write(address, value)
        await self.async_request_refresh()


async def discover(client: Smart365Client) -> Topology:
    """Find zones, modules and rooms configured on the system."""
    topology = Topology()
    num_zones = (await client.read_registers(REG_NUM_ZONES, 1))[0]
    topology.zones = list(range(max(num_zones, 1)))

    modules: set[int] = set()
    for zone in topology.zones:
        bitmap = (await client.read_registers(zone_address(zone, ZONE_MODULE_BITMAP), 1))[0]
        modules.update(m for m in range(MAX_MODULES) if bitmap & (1 << m))
    if not modules:
        modules = {0}
    topology.modules = sorted(modules)

    for module in topology.modules:
        info = await client.read_registers(module_address(module), MODULE_BLOCK_LEN)
        num_sensors = info[MODULE_NUM_SENSORS]
        found: list[Room] = []
        for index in range(ROOMS_PER_MODULE):
            try:
                regs = await client.read_registers(room_address(module, index), ROOM_BLOCK_LEN)
            except Smart365ModbusException:
                continue
            if regs[ROOM_SENSOR_TYPE] != 0:
                found.append(
                    Room(module, index, regs[ROOM_ZONE_ID], regs[ROOM_SENSOR_TYPE])
                )
        if not found:
            # Fall back on the sensor count when sensor types are not reported.
            for index in range(min(num_sensors, ROOMS_PER_MODULE)):
                regs = await client.read_registers(room_address(module, index), ROOM_BLOCK_LEN)
                found.append(
                    Room(module, index, regs[ROOM_ZONE_ID], regs[ROOM_SENSOR_TYPE])
                )
        topology.rooms.extend(found)
    return topology
