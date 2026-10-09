"""Decode a known register snapshot through the model."""

from modbus_connection.mock import MockModbusUnit

from sunsynk_modbus import InverterState, SunsynkInverter


def _snapshot() -> dict[int, int]:
    regs = {address: 0 for address in range(0, 200)}
    regs.update(
        {
            0: 0x0003,
            # "2201234567": two ASCII characters per register, high byte first.
            3: 0x3232,
            4: 0x3031,
            5: 0x3233,
            6: 0x3435,
            7: 0x3637,
            16: 36000,
            17: 0,  # 3600.0 W rated, low word first
            59: 2,
            60: 123,  # 12.3 kWh
            63: 0x86A0,
            64: 0x0001,  # 100000 -> 10000.0 kWh
            78: 0x2710,
            80: 0x0001,  # (1 << 16 | 10000) -> 7553.6 kWh
            79: 5001,
            91: 1350,  # 35.0 °C
            103: 0,
            104: 0x0004,  # bit 18 -> F19
            105: 0,
            106: 0,
            109: 3105,
            110: 52,
            150: 2405,
            160: 150,
            161: 0xFFF6,  # 1.50 + -0.10 A
            172: 0xFF38,  # -200 W (exporting)
            178: 640,
            182: 1215,  # 21.5 °C
            183: 5312,
            184: 87,
            186: 1500,
            187: 200,
            190: 0xFE0C,  # -500 W
            194: 1,
        }
    )
    return regs


async def test_decodes_snapshot(mock_modbus_unit: MockModbusUnit) -> None:
    mock_modbus_unit.load_raw({"holding": _snapshot()})
    inverter = SunsynkInverter(mock_modbus_unit)

    report = await inverter.async_update()
    assert report.complete

    assert inverter.identity.serial_number == "2201234567"
    assert inverter.identity.rated_power == 3600.0

    r = inverter.readings
    assert r.state is InverterState.NORMAL
    assert r.grid_frequency == 50.01
    assert r.heatsink_temperature == 35.0
    assert r.battery_temperature == 21.5
    assert r.environment_temperature is None  # raw 0: no sensor fitted
    assert r.pv1_voltage == 310.5
    assert r.pv_power == 1700
    assert r.grid_ct_power == -200
    assert r.grid_current == 1.4
    assert r.battery_power == -500
    assert r.battery_voltage == 53.12
    assert r.battery_soc == 87
    assert r.grid_connected is True
    assert r.active_faults == ["F19"]

    e = inverter.energy
    assert e.day_active_energy == 12.3
    assert e.total_active_energy == 10000.0
    assert e.total_grid_import == 7553.6
