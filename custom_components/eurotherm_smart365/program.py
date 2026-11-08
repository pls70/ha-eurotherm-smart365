"""Weekly program run by Home Assistant.

The SmartComfort 365 does not expose its own weekly program over Modbus, so
Home Assistant can run one instead. Each zone has three temperature levels
(like the panel) and two Home Assistant `schedule` helpers: when the level 3
schedule is on the zone uses level 3, otherwise when the level 2 schedule is
on it uses level 2, otherwise level 1. When the level changes, every room of
the zone is put in manual mode at that level's temperature. Turning the
program off puts the rooms back on the panel's own program.

Other thermostats (for example air conditioners or bathroom heaters from
other integrations) can be added to a zone's program: they get the same
level temperature, but only while they are on in a heating mode. The
program never turns them on or off.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
import logging

from homeassistant.components.climate import (
    DOMAIN as CLIMATE_DOMAIN,
    SERVICE_SET_TEMPERATURE,
    HVACMode,
)
from homeassistant.const import ATTR_ENTITY_ID, ATTR_TEMPERATURE, STATE_ON
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event

from .const import (
    OPERATIVE_HEATING,
    ROOM_MANUAL_TEMP,
    ROOM_MODE,
    ROOM_MODE_AUTO,
    ROOM_MODE_MANUAL,
    ZONE_MODE,
    ZONE_MODE_HOME,
    ZONE_OPERATIVE_MODE,
    from_temperature,
    room_address,
)

_LOGGER = logging.getLogger(__name__)

LEVELS = (1, 2, 3)
DEFAULT_LEVEL_TEMPS = {1: 17.0, 2: 20.0, 3: 21.0}
CONF_LEVEL2_SCHEDULE = "zone{zone}_level2_schedule"
CONF_LEVEL3_SCHEDULE = "zone{zone}_level3_schedule"
CONF_CLIMATES = "zone{zone}_climates"
HEATING_HVAC_MODES = {HVACMode.HEAT, HVACMode.AUTO, HVACMode.HEAT_COOL}


class ZoneProgram:
    """Home Assistant weekly program for one zone."""

    def __init__(self, coordinator, zone: int, options: dict) -> None:
        self.coordinator = coordinator
        self.hass: HomeAssistant = coordinator.hass
        self.zone = zone
        self.enabled = False
        self.temps: dict[int, float] = dict(DEFAULT_LEVEL_TEMPS)
        self.schedules: dict[int, str | None] = {
            2: options.get(CONF_LEVEL2_SCHEDULE.format(zone=zone)) or None,
            3: options.get(CONF_LEVEL3_SCHEDULE.format(zone=zone)) or None,
        }
        self.climates: list[str] = list(options.get(CONF_CLIMATES.format(zone=zone)) or [])
        self._listeners: list[Callable[[], None]] = []
        self._unsubs: list[CALLBACK_TYPE] = []
        self._started = False
        self._last_zone_active: bool | None = None
        self._lock = asyncio.Lock()

    # --- state ---------------------------------------------------------

    @property
    def level(self) -> int:
        """Level currently selected by the schedules."""
        for level in (3, 2):
            entity_id = self.schedules[level]
            if entity_id and (state := self.hass.states.get(entity_id)) and state.state == STATE_ON:
                return level
        return 1

    @property
    def target(self) -> float:
        """Temperature of the current level."""
        return self.temps[self.level]

    @property
    def zone_active(self) -> bool:
        """Whether the program may drive the rooms (zone at home, heating)."""
        regs = (self.coordinator.data.zones if self.coordinator.data else {}).get(self.zone)
        return (
            regs is not None
            and regs[ZONE_MODE] == ZONE_MODE_HOME
            and regs[ZONE_OPERATIVE_MODE] == OPERATIVE_HEATING
        )

    @callback
    def async_add_listener(self, listener: Callable[[], None]) -> CALLBACK_TYPE:
        """Be told when the program level or settings change."""
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    @callback
    def _notify(self) -> None:
        for listener in list(self._listeners):
            listener()

    # --- lifecycle -----------------------------------------------------

    @callback
    def async_start(self) -> None:
        """Follow the schedules and the zone state, and apply the program once."""
        self._started = True
        entity_ids = [e for e in self.schedules.values() if e]
        if entity_ids:
            self._unsubs.append(
                async_track_state_change_event(self.hass, entity_ids, self._schedule_changed)
            )
        if self.climates:
            self._unsubs.append(
                async_track_state_change_event(self.hass, self.climates, self._climate_changed)
            )
        self._unsubs.append(self.coordinator.async_add_listener(self._coordinator_updated))
        self._last_zone_active = self.zone_active
        self._schedule_apply()

    @callback
    def async_stop(self) -> None:
        """Stop following the schedules."""
        self._started = False
        while self._unsubs:
            self._unsubs.pop()()

    @callback
    def _schedule_changed(self, event: Event) -> None:
        self._notify()
        self._schedule_apply()

    @callback
    def _climate_changed(self, event: Event) -> None:
        old, new = event.data["old_state"], event.data["new_state"]
        if (
            new is not None
            and new.state in HEATING_HVAC_MODES
            and (old is None or old.state not in HEATING_HVAC_MODES)
        ):
            # A thermostat was just turned on: give it the current level.
            self._schedule_apply()

    @callback
    def _coordinator_updated(self) -> None:
        active = self.zone_active
        if active and self._last_zone_active is False:
            # Zone back at home / in heating: apply the current level again.
            self._schedule_apply()
        self._last_zone_active = active

    @callback
    def _schedule_apply(self) -> None:
        if self._started and self.enabled:
            self.hass.async_create_task(self.async_apply(), eager_start=False)

    # --- settings ------------------------------------------------------

    async def async_set_enabled(self, enabled: bool) -> None:
        """Turn the Home Assistant program on or off."""
        was = self.enabled
        self.enabled = enabled
        self._notify()
        if not self._started:
            return
        if enabled:
            await self.async_apply()
        elif was:
            await self.async_release()

    async def async_set_temperature(self, level: int, value: float) -> None:
        """Change the temperature of a level."""
        self.temps[level] = value
        self._notify()
        if self._started and self.enabled and self.level == level:
            await self.async_apply()

    # --- actions -------------------------------------------------------

    def _zone_rooms(self):
        return [r for r in self.coordinator.topology.rooms if r.zone == self.zone]

    async def async_apply(self) -> None:
        """Put the zone's rooms in manual mode at the current level's temperature."""
        async with self._lock:
            await self._async_apply()

    async def _async_apply(self) -> None:
        if not self.enabled or not self.zone_active:
            return
        target = self.target
        raw = from_temperature(target)
        wrote = False
        for room in self._zone_rooms():
            regs = self.coordinator.data.rooms.get(room.key)
            if regs is None or regs[ROOM_MODE] not in (ROOM_MODE_AUTO, ROOM_MODE_MANUAL):
                # Off, or a panel-only mode (party, holiday...): leave it alone.
                continue
            if regs[ROOM_MODE] == ROOM_MODE_MANUAL and regs[ROOM_MANUAL_TEMP] == raw:
                continue
            await self.coordinator.client_write(
                room_address(room.module, room.index, ROOM_MANUAL_TEMP), raw
            )
            await self.coordinator.client_write(
                room_address(room.module, room.index, ROOM_MODE), ROOM_MODE_MANUAL
            )
            wrote = True
        if wrote:
            _LOGGER.debug("Zone %s: program level %s, %.1f °C", self.zone, self.level, target)
            await self.coordinator.async_request_refresh()
        await self._async_apply_climates(target)

    async def _async_apply_climates(self, target: float) -> None:
        """Give the other thermostats of the zone the level temperature."""
        for entity_id in self.climates:
            state = self.hass.states.get(entity_id)
            if state is None or state.state not in HEATING_HVAC_MODES:
                continue
            if state.attributes.get(ATTR_TEMPERATURE) == target:
                continue
            data = {ATTR_ENTITY_ID: entity_id, ATTR_TEMPERATURE: target}
            try:
                await self.hass.services.async_call(
                    CLIMATE_DOMAIN, SERVICE_SET_TEMPERATURE, data, blocking=True
                )
            except Exception:  # noqa: BLE001 - one device must not stop the others
                _LOGGER.warning("Zone %s: cannot set %s to %.1f °C", self.zone, entity_id, target)

    async def async_release(self) -> None:
        """Give the zone's rooms back to the panel's own program."""
        async with self._lock:
            await self._async_release()

    async def _async_release(self) -> None:
        wrote = False
        for room in self._zone_rooms():
            regs = self.coordinator.data.rooms.get(room.key)
            if regs is not None and regs[ROOM_MODE] == ROOM_MODE_MANUAL:
                await self.coordinator.client_write(
                    room_address(room.module, room.index, ROOM_MODE), ROOM_MODE_AUTO
                )
                wrote = True
        if wrote:
            await self.coordinator.async_request_refresh()
