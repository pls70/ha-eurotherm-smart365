"""Sensors for the Eurotherm Smart365 integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    MODULE_FLOW_SETPOINT,
    MODULE_FLOW_TEMP,
    ROOM_DEWPOINT,
    ROOM_HUMIDITY,
    ROOM_TARGET_TEMP,
    ROOM_TEMP,
    SENSOR_TYPE_TEMP_HUMIDITY,
    to_temperature,
)
from .coordinator import Room, Smart365ConfigEntry, Smart365Coordinator
from .entity import Smart365Entity, Smart365RoomEntity


@dataclass(frozen=True, kw_only=True)
class RoomSensorDescription(SensorEntityDescription):
    """Describes a room sensor."""

    value_fn: Callable[[list[int]], float | int]
    needs_humidity: bool = False


TEMPERATURE = dict(
    device_class=SensorDeviceClass.TEMPERATURE,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    suggested_display_precision=1,
)

ROOM_SENSORS = (
    RoomSensorDescription(
        key="temperature",
        value_fn=lambda regs: to_temperature(regs[ROOM_TEMP]),
        **TEMPERATURE,
    ),
    RoomSensorDescription(
        key="target_temperature",
        translation_key="target_temperature",
        value_fn=lambda regs: to_temperature(regs[ROOM_TARGET_TEMP]),
        **TEMPERATURE,
    ),
    RoomSensorDescription(
        key="humidity",
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda regs: regs[ROOM_HUMIDITY],
        needs_humidity=True,
    ),
    RoomSensorDescription(
        key="dewpoint",
        translation_key="dewpoint",
        value_fn=lambda regs: to_temperature(regs[ROOM_DEWPOINT]),
        needs_humidity=True,
        **TEMPERATURE,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: Smart365ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up sensors."""
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = [OutdoorTemperatureSensor(coordinator)]
    for module in coordinator.topology.modules:
        # A module without a flow probe always reports 0: skip the sensor.
        if coordinator.data.modules[module][MODULE_FLOW_TEMP] != 0:
            entities.append(
                ModuleSensor(coordinator, module, "flow_temperature", MODULE_FLOW_TEMP)
            )
        entities.append(ModuleSensor(coordinator, module, "flow_setpoint", MODULE_FLOW_SETPOINT))
    for room in coordinator.topology.rooms:
        has_humidity = room.sensor_type == SENSOR_TYPE_TEMP_HUMIDITY
        entities.extend(
            RoomSensor(coordinator, room, description)
            for description in ROOM_SENSORS
            if has_humidity or not description.needs_humidity
        )
    async_add_entities(entities)


class OutdoorTemperatureSensor(Smart365Entity, SensorEntity):
    """Outdoor temperature used by the panel."""

    _attr_translation_key = "outdoor_temperature"
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator: Smart365Coordinator) -> None:
        super().__init__(coordinator, "outdoor_temperature")

    @property
    def native_value(self) -> float | None:
        raw = self.coordinator.data.outdoor_temp_raw
        return None if raw is None else to_temperature(raw)


class ModuleSensor(Smart365Entity, SensorEntity):
    """Water flow temperature of a module (manifold)."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_suggested_display_precision = 1
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: Smart365Coordinator, module: int, key: str, field: int) -> None:
        super().__init__(coordinator, f"module{module}_{key}")
        self._module = module
        self._field = field
        self._attr_translation_key = key
        self._attr_translation_placeholders = {"module": str(module + 1)}

    @property
    def available(self) -> bool:
        return super().available and self._module in self.coordinator.data.modules

    @property
    def native_value(self) -> float | None:
        return to_temperature(self.coordinator.data.modules[self._module][self._field])


class RoomSensor(Smart365RoomEntity, SensorEntity):
    """A room measurement."""

    entity_description: RoomSensorDescription

    def __init__(
        self, coordinator: Smart365Coordinator, room: Room, description: RoomSensorDescription
    ) -> None:
        super().__init__(coordinator, room, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float | int | None:
        return self.entity_description.value_fn(self.room_regs)
