"""Decode a snapshot taken from a real 3.6K-SG01LP1, and the poll behaviour around it."""

from typing import Any

import pytest
from modbus_connection import IllegalDataAddressError, ModbusTimeoutError
from modbus_connection.mock import MockModbusUnit

from sunsynk_modbus import InverterState, SunsynkInverter


async def test_real_inverter_snapshot(
    mock_modbus_unit: MockModbusUnit, sg01lp1_raw: dict[str, Any]
) -> None:
    mock_modbus_unit.load_raw(sg01lp1_raw)
    inverter = SunsynkInverter(mock_modbus_unit)

    report = await inverter.async_update()

    assert report.updated == {"readings", "energy"}
    assert inverter.identity.serial_number == "2201234567"
    assert inverter.identity.device_type == 3
    assert inverter.identity.rated_power == 3600.0

    r = inverter.readings
    assert r.state is InverterState.NORMAL
    assert r.environment_temperature is None
    assert r.battery_soc == 21
    assert r.battery_voltage == 52.54
    assert r.battery_power == 114  # discharging
    assert r.grid_ct_power == 20  # importing
    assert r.load_power == 559
    assert r.inverter_power == 539
    assert r.pv_power == 517
    assert r.grid_connected is True
    assert r.active_faults == []

    e = inverter.energy
    assert e.total_grid_import == 14007.6
    assert e.total_grid_export == 2504.5
    assert e.total_pv_energy == 13025.2
    assert e.total_battery_charge == 5254.3
    assert e.total_battery_discharge == 4291.1
    assert e.total_load_energy == 21540.0


async def test_readings_poll_leaves_energy_unread(
    mock_modbus_unit: MockModbusUnit, sg01lp1_raw: dict[str, Any]
) -> None:
    mock_modbus_unit.load_raw(sg01lp1_raw)
    inverter = SunsynkInverter(mock_modbus_unit)

    report = await inverter.async_update_readings()

    assert report.updated == {"readings"}
    assert inverter.readings.load_power == 559
    assert inverter.energy.total_grid_import is None
    assert inverter.identity.serial_number == "2201234567"


async def test_failed_energy_read_is_reported(
    mock_modbus_unit: MockModbusUnit, sg01lp1_raw: dict[str, Any]
) -> None:
    mock_modbus_unit.load_raw(sg01lp1_raw)
    mock_modbus_unit.fail_read(63, IllegalDataAddressError(0x03))  # energy block only
    inverter = SunsynkInverter(mock_modbus_unit)

    report = await inverter.async_update()

    assert report.updated == {"readings"}
    assert set(report.failed) == {"energy"}


async def test_energy_poll_leaves_readings_unread(
    mock_modbus_unit: MockModbusUnit, sg01lp1_raw: dict[str, Any]
) -> None:
    mock_modbus_unit.load_raw(sg01lp1_raw)
    inverter = SunsynkInverter(mock_modbus_unit)

    report = await inverter.async_update_energy()

    assert report.updated == {"energy"}
    assert inverter.energy.day_load_energy == 5.1
    assert inverter.readings.load_power is None


async def test_silent_inverter_raises_timeout(mock_modbus_unit: MockModbusUnit) -> None:
    mock_modbus_unit.fail_requests(ModbusTimeoutError("no reply"))
    inverter = SunsynkInverter(mock_modbus_unit)

    with pytest.raises(ModbusTimeoutError):
        await inverter.async_update()


async def test_fault_bits_map_to_codes(
    mock_modbus_unit: MockModbusUnit, sg01lp1_raw: dict[str, Any]
) -> None:
    sg01lp1_raw["holding"]["103"] = 0x0001  # bit 0 -> F01
    sg01lp1_raw["holding"]["105"] = 0x0004  # bit 34 -> F35 (no AC grid)
    mock_modbus_unit.load_raw(sg01lp1_raw)
    inverter = SunsynkInverter(mock_modbus_unit)

    await inverter.async_update_readings()

    assert inverter.readings.active_faults == ["F01", "F35"]


def test_derived_values_are_none_before_a_poll(mock_modbus_unit: MockModbusUnit) -> None:
    inverter = SunsynkInverter(mock_modbus_unit)

    assert inverter.readings.pv_power is None
    assert inverter.readings.grid_current is None
    assert inverter.readings.grid_connected is None
    assert inverter.readings.active_faults == []
    assert inverter.energy.total_grid_import is None
