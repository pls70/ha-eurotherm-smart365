"""Tests for the Eurotherm Smart365 integration."""

from __future__ import annotations

from homeassistant import config_entries
from homeassistant.components.climate import HVACMode
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_mock_service

from custom_components.eurotherm_smart365.const import CONF_UNIT_ID, DOMAIN

from .fake_device import FakeSmart365


def entry_data(device: FakeSmart365) -> dict:
    return {CONF_HOST: "127.0.0.1", CONF_PORT: device.port, CONF_UNIT_ID: 1}


async def setup(hass: HomeAssistant, device: FakeSmart365) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, data=entry_data(device), unique_id="65538")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_config_flow(hass: HomeAssistant, device: FakeSmart365) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(result["flow_id"], entry_data(device))
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == str((1 << 16) | 2)


async def test_config_flow_cannot_connect(hass: HomeAssistant, device: FakeSmart365) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    data = entry_data(device) | {CONF_PORT: 1}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], data)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_setup_discovers_rooms(hass: HomeAssistant, device: FakeSmart365) -> None:
    await setup(hass, device)
    climates = hass.states.async_entity_ids("climate")
    assert len(climates) == 6
    state = hass.states.get("climate.stanza_1")
    assert state.state == HVACMode.AUTO
    assert state.attributes["current_temperature"] == 19.0
    assert state.attributes["temperature"] == 20.0
    assert hass.states.get("sensor.eurotherm_smart365_outdoor_temperature") or any(
        s.attributes.get("unit_of_measurement") == "°C" and "outdoor" in s.entity_id
        for s in hass.states.async_all("sensor")
    )
    assert hass.states.get("select.zona_1_mode").state == "home"
    # Temperature-only sensors: no humidity entities
    assert not [s for s in hass.states.async_entity_ids("sensor") if "humidity" in s]
    registry = er.async_get(hass)
    assert registry.async_get("switch.zona_1_air_renewal_boost").disabled


async def test_set_temperature(hass: HomeAssistant, device: FakeSmart365) -> None:
    await setup(hass, device)
    await hass.services.async_call(
        "climate", "set_temperature",
        {"entity_id": "climate.stanza_2", "temperature": 21.5}, blocking=True,
    )
    assert device.writes == [(1610, 215), (1609, 2)]
    await hass.async_block_till_done()
    assert hass.states.get("climate.stanza_2").state == HVACMode.HEAT

    device.writes.clear()
    await hass.services.async_call(
        "climate", "set_hvac_mode",
        {"entity_id": "climate.stanza_2", "hvac_mode": "auto"}, blocking=True,
    )
    assert device.writes == [(1609, 1)]


async def test_zone_off_and_season(hass: HomeAssistant, device: FakeSmart365) -> None:
    await setup(hass, device)
    await hass.services.async_call(
        "select", "select_option",
        {"entity_id": "select.zona_1_mode", "option": "off"}, blocking=True,
    )
    assert device.writes == [(102, 1)]
    await hass.async_block_till_done()
    assert hass.states.get("climate.stanza_1").state == HVACMode.OFF

    device.registers[101] = 0
    await hass.config_entries.async_reload(
        hass.config_entries.async_entries(DOMAIN)[0].entry_id
    )
    await hass.async_block_till_done()
    device.registers[102] = 0
    await hass.config_entries.async_entries(DOMAIN)[0].runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get("climate.stanza_1").attributes["hvac_modes"] == ["auto", "cool"]


async def test_negative_outdoor_temperature(hass: HomeAssistant, device: FakeSmart365) -> None:
    device.registers[58] = 65536 - 35
    await setup(hass, device)
    outdoor = [s for s in hass.states.async_all("sensor") if "outdoor" in s.entity_id]
    assert outdoor and float(outdoor[0].state) == -3.5


def flow_sensors(hass: HomeAssistant, key: str) -> list[str]:
    registry = er.async_get(hass)
    return [e.entity_id for e in registry.entities.values() if e.unique_id.endswith(key)]


async def test_flow_probe_present(hass: HomeAssistant, device: FakeSmart365) -> None:
    await setup(hass, device)
    assert flow_sensors(hass, "module0_flow_temperature")
    assert flow_sensors(hass, "module0_flow_setpoint")


async def test_no_flow_probe(hass: HomeAssistant, device: FakeSmart365) -> None:
    device.registers[1146] = 0
    await setup(hass, device)
    assert not flow_sensors(hass, "module0_flow_temperature")
    assert flow_sensors(hass, "module0_flow_setpoint")


async def test_read_registers_service(hass: HomeAssistant, device: FakeSmart365) -> None:
    await setup(hass, device)
    response = await hass.services.async_call(
        DOMAIN,
        "read_registers",
        {"address": 100, "count": 8},
        blocking=True,
        return_response=True,
    )
    assert response["count"] == 8
    regs = response["registers"]
    assert regs["101"] == 1
    assert regs["105"] == 1
    # Registers the panel refuses come back as null.
    assert regs["106"] is None and regs["107"] is None


ROOM_MODE_REGS = [1209 + 400 * r for r in range(6)]
ROOM_MANUAL_REGS = [1210 + 400 * r for r in range(6)]


def manual_writes(temp: int) -> list[tuple[int, int]]:
    return [
        w for r in range(6) for w in ((ROOM_MANUAL_REGS[r], temp), (ROOM_MODE_REGS[r], 2))
    ]


async def refresh(hass: HomeAssistant) -> None:
    await hass.async_block_till_done()
    await hass.config_entries.async_entries(DOMAIN)[0].runtime_data.async_refresh()
    await hass.async_block_till_done()


async def test_ha_program(hass: HomeAssistant, device: FakeSmart365) -> None:
    hass.states.async_set("schedule.livello_2", "off")
    hass.states.async_set("schedule.livello_3", "off")
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=entry_data(device),
        unique_id="65538",
        options={
            "zone0_level2_schedule": "schedule.livello_2",
            "zone0_level3_schedule": "schedule.livello_3",
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    switch = "switch.zona_1_home_assistant_program"
    sensor = "sensor.zona_1_program_level"
    assert hass.states.get(switch).state == "off"
    assert hass.states.get(sensor).state == "level1"
    assert hass.states.get("number.zona_1_program_level_1").state == "17.0"

    # Schedules alone do nothing while the program is off.
    hass.states.async_set("schedule.livello_2", "on")
    await refresh(hass)
    assert device.writes == []
    assert hass.states.get(sensor).state == "level2"
    hass.states.async_set("schedule.livello_2", "off")
    await refresh(hass)

    await hass.services.async_call("switch", "turn_on", {"entity_id": switch}, blocking=True)
    await refresh(hass)
    assert device.writes == manual_writes(170)
    assert hass.states.get("climate.stanza_1").state == HVACMode.HEAT

    device.writes.clear()
    hass.states.async_set("schedule.livello_2", "on")
    await refresh(hass)
    assert device.writes == manual_writes(200)

    # Level 3 wins over level 2.
    device.writes.clear()
    hass.states.async_set("schedule.livello_3", "on")
    await refresh(hass)
    assert device.writes == manual_writes(210)
    assert hass.states.get(sensor).state == "level3"

    # Changing the active level's temperature applies it at once.
    device.writes.clear()
    await hass.services.async_call(
        "number", "set_value",
        {"entity_id": "number.zona_1_program_level_3", "value": 21.5}, blocking=True,
    )
    await refresh(hass)
    assert device.writes == manual_writes(215)

    # Zone away: the program leaves the rooms alone, and catches up when home again.
    device.writes.clear()
    device.registers[102] = 2
    await refresh(hass)
    hass.states.async_set("schedule.livello_3", "off")
    await refresh(hass)
    assert device.writes == []
    device.registers[102] = 0
    await refresh(hass)
    await refresh(hass)
    assert device.writes == manual_writes(200)

    # Off: rooms go back to the panel's program.
    device.writes.clear()
    await hass.services.async_call("switch", "turn_off", {"entity_id": switch}, blocking=True)
    await refresh(hass)
    assert device.writes == [(reg, 1) for reg in ROOM_MODE_REGS]


async def test_options_flow(hass: HomeAssistant, device: FakeSmart365) -> None:
    hass.states.async_set("schedule.livello_2", "off")
    entry = await setup(hass, device)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"zone0_level2_schedule": "schedule.livello_2"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    program = hass.config_entries.async_entries(DOMAIN)[0].runtime_data.programs[0]
    assert program.schedules == {2: "schedule.livello_2", 3: None}


async def test_ha_program_other_thermostats(hass: HomeAssistant, device: FakeSmart365) -> None:
    hass.states.async_set("schedule.livello_2", "off")
    hass.states.async_set("climate.gree", "heat", {"temperature": 22})
    hass.states.async_set("climate.stufetta", "off", {"temperature": 22})
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=entry_data(device),
        unique_id="65538",
        options={
            "zone0_level2_schedule": "schedule.livello_2",
            "zone0_climates": ["climate.gree", "climate.stufetta"],
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    # Replace the real climate service (loaded by the integration) with a recorder.
    calls = async_mock_service(hass, "climate", "set_temperature")

    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": "switch.zona_1_home_assistant_program"}, blocking=True
    )
    await refresh(hass)
    # Only the thermostat that is on gets the level temperature.
    assert [(c.data["entity_id"], c.data["temperature"]) for c in calls] == [("climate.gree", 17.0)]

    calls.clear()
    hass.states.async_set("climate.gree", "heat", {"temperature": 17.0})
    hass.states.async_set("schedule.livello_2", "on")
    await refresh(hass)
    assert [(c.data["entity_id"], c.data["temperature"]) for c in calls] == [("climate.gree", 20.0)]

    # A heater turned on later gets the current level at once.
    calls.clear()
    hass.states.async_set("climate.gree", "heat", {"temperature": 20.0})
    hass.states.async_set("climate.stufetta", "heat", {"temperature": 22})
    await refresh(hass)
    assert [(c.data["entity_id"], c.data["temperature"]) for c in calls] == [
        ("climate.stufetta", 20.0)
    ]
