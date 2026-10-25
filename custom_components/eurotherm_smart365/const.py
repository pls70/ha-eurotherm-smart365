"""Constants for the Eurotherm Smart365 integration.

Register map from "SmartComfort 365 - Modbus interface for home automation" Rev.05.
"""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "eurotherm_smart365"
MANUFACTURER = "Eurotherm"
MODEL = "SmartComfort 365"

DEFAULT_PORT = 502
DEFAULT_UNIT_ID = 1
DEFAULT_SCAN_INTERVAL = timedelta(seconds=30)

CONF_UNIT_ID = "unit_id"

# System information
REG_SERIAL_HIGH = 50
REG_OUTDOOR_TEMP = 58
REG_NUM_ZONES = 59

# Zone registers (zone n is at offset ZONE_OFFSET * n)
REG_ZONE_BASE = 100
ZONE_OFFSET = 130
ZONE_BLOCK_LEN = 6  # 100..105
ZONE_OPERATIVE_MODE = 1  # 0 cooling, 1 heating
ZONE_MODE = 2  # 0 home, 1 off, 2 away, 3 holiday (RO)
ZONE_AIR_BOOST = 3
ZONE_MODULE_BITMAP = 5

OPERATIVE_COOLING = 0
OPERATIVE_HEATING = 1

ZONE_MODE_HOME = 0
ZONE_MODE_OFF = 1
ZONE_MODE_AWAY = 2
ZONE_MODE_HOLIDAY = 3

# Module (base) registers (module n is at offset MODULE_OFFSET * n)
MAX_MODULES = 8
MODULE_OFFSET = 3260
REG_MODULE_BASE = 1140
MODULE_BLOCK_LEN = 7  # 1140..1146
MODULE_NUM_SENSORS = 2
MODULE_TYPE = 4
MODULE_FLOW_SETPOINT = 5
MODULE_FLOW_TEMP = 6

# Room registers (room r of module n is at REG_ROOM_BASE + ROOM_OFFSET * r + MODULE_OFFSET * n)
ROOMS_PER_MODULE = 8
REG_ROOM_BASE = 1200
ROOM_OFFSET = 400
ROOM_BLOCK_LEN = 11  # 1200..1210
ROOM_ZONE_ID = 2
ROOM_SENSOR_TYPE = 3
ROOM_SENSOR_ERRORS = 4
ROOM_TEMP = 5
ROOM_HUMIDITY = 6
ROOM_DEWPOINT = 7
ROOM_TARGET_TEMP = 8
ROOM_MODE = 9
ROOM_MANUAL_TEMP = 10

SENSOR_TYPE_TEMP = 1
SENSOR_TYPE_TEMP_HUMIDITY = 2

ROOM_MODE_OFF = 0
ROOM_MODE_AUTO = 1
ROOM_MODE_MANUAL = 2
ROOM_MODE_NAMES = {
    0: "off",
    1: "auto",
    2: "manual",
    3: "manual_temporary",
    4: "party",
    5: "early_bird",
    6: "goodnight",
}

# Sensor error bit mask (register x204)
ERR_DISCONNECTED = 1
ERR_CONDENSATION = 8
ERR_HIGH_HUMIDITY = 16
ERR_TEMP_MEASURE = 32
ERR_HUMIDITY_MEASURE = 64
ERR_HUMIDITY_SCALE = 256
ERR_BATTERY = 512
ERR_SENSOR_FAULT = ERR_DISCONNECTED | ERR_TEMP_MEASURE | ERR_HUMIDITY_MEASURE | ERR_HUMIDITY_SCALE


def zone_address(zone: int, field: int = 0) -> int:
    """Return the register address of a zone field."""
    return REG_ZONE_BASE + ZONE_OFFSET * zone + field


def module_address(module: int, field: int = 0) -> int:
    """Return the register address of a module field."""
    return REG_MODULE_BASE + MODULE_OFFSET * module + field


def room_address(module: int, room: int, field: int = 0) -> int:
    """Return the register address of a room field."""
    return REG_ROOM_BASE + ROOM_OFFSET * room + MODULE_OFFSET * module + field


def to_temperature(raw: int) -> float:
    """Convert a raw [0.1 °C] register value, handling negative values."""
    if raw > 60000:
        raw -= 65536
    return raw / 10


def from_temperature(value: float) -> int:
    """Convert a temperature in °C to a raw [0.1 °C] register value."""
    return round(value * 10) & 0xFFFF
