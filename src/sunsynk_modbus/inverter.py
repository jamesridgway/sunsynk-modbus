"""Sunsynk single-phase hybrid inverter (SG01LP1 family) register map.

Every value is a holding register (FC03). Addresses and scaling follow the
community map in kellerza/sunsynk (definitions/single_phase.py):

- 32-bit counters are low word first.
- Temperatures are ``raw * 0.1 - 100`` from an unsigned register.
- Power and current registers are signed. Verified on a 3.6K-SG01LP1:
  battery_power / battery_current are positive when discharging, and
  grid_power / grid_ct_power are positive when importing from the grid.
"""

from __future__ import annotations

import contextlib
from enum import IntEnum

from modbus_connection import ModbusExceptionError, ModbusUnit
from modbus_connection.model import (
    Component,
    Device,
    NumberField,
    UpdateReport,
    enum,
    gauge,
    integer,
    raw_register,
    string,
    uint32,
)

# The inverter answers fine with long reads over RS485, but some gateways cap
# them lower. Lower this if you see illegal-address or timeout errors.
MAX_SPAN = 60

# Per-request timeout. One 60-register read takes ~150 ms at 9600 baud; the
# rest is headroom for Wi-Fi and the gateway's own 2 s RTU timeout.
REQUEST_TIMEOUT = 3.0


class InverterState(IntEnum):
    """Overall inverter state (register 59)."""

    STANDBY = 0
    SELF_CHECK = 1
    NORMAL = 2
    ALARM = 3
    FAULT = 4
    ACTIVATING = 5


class BatteryType(IntEnum):
    """Battery chemistry setting (register 200)."""

    LEAD_ACID = 0
    LITHIUM = 1


class BatteryMode(IntEnum):
    """How the inverter manages the battery (register 213).

    This is an installer setting, not a live detection: no register reports
    whether a battery is physically connected.
    """

    VOLTAGE = 0
    CAPACITY = 1
    NO_BATTERY = 2


def _temperature(address: int) -> NumberField[float]:
    # Raw 0 (-100 °C) is what an absent sensor reads, so report it as None.
    return gauge(address, 0.1, offset=-100, signed=False, nan=0, unit="°C")


class Identity(Component):
    """Values that never change; read once at setup."""

    max_span = MAX_SPAN

    device_type = integer(0, signed=False)
    protocol_version = raw_register(2)
    serial_number = string(3, 5)
    rated_power = uint32(16, scale=0.1, word_order="little", unit="W")


class BatterySettings(Component):
    """Battery settings; read once at setup."""

    max_span = MAX_SPAN

    battery_type = enum(200, BatteryType)
    battery_mode = enum(213, BatteryMode)


class Readings(Component):
    """Live power, voltage, current, temperature and state values."""

    max_span = MAX_SPAN

    state = enum(59, InverterState)
    grid_frequency = gauge(79, 0.01, signed=False, unit="Hz")

    dc_transformer_temperature = _temperature(90)
    heatsink_temperature = _temperature(91)
    environment_temperature = _temperature(95)

    fault_word_1 = raw_register(103)
    fault_word_2 = raw_register(104)
    fault_word_3 = raw_register(105)
    fault_word_4 = raw_register(106)

    pv1_voltage = gauge(109, 0.1, signed=False, unit="V")
    pv1_current = gauge(110, 0.1, signed=False, unit="A")
    pv2_voltage = gauge(111, 0.1, signed=False, unit="V")
    pv2_current = gauge(112, 0.1, signed=False, unit="A")

    grid_voltage = gauge(150, 0.1, signed=False, unit="V")
    inverter_voltage = gauge(154, 0.1, signed=False, unit="V")
    grid_current_l1 = gauge(160, 0.01, unit="A")
    grid_current_l2 = gauge(161, 0.01, unit="A")
    inverter_current = gauge(164, 0.01, unit="A")
    aux_power = integer(166, unit="W")
    grid_ld_power = integer(167, unit="W")
    grid_power = integer(169, unit="W")  # + import, - export
    grid_ct_power = integer(172, unit="W")  # + import, - export
    inverter_power = integer(175, unit="W")
    load_power = integer(178, unit="W")

    battery_temperature = _temperature(182)
    battery_voltage = gauge(183, 0.01, signed=False, unit="V")
    battery_soc = integer(184, signed=False, unit="%")
    pv1_power = integer(186, unit="W")
    pv2_power = integer(187, unit="W")
    battery_power = integer(190, unit="W")  # + discharge, - charge
    battery_current = gauge(191, 0.01, unit="A")  # + discharge, - charge
    load_frequency = gauge(192, 0.01, signed=False, unit="Hz")
    inverter_frequency = gauge(193, 0.01, signed=False, unit="Hz")
    grid_connected_raw = raw_register(194)

    @property
    def pv_power(self) -> int | None:
        """Total PV power across both MPPTs."""
        if self.pv1_power is None or self.pv2_power is None:
            return None
        return self.pv1_power + self.pv2_power

    @property
    def grid_current(self) -> float | None:
        if self.grid_current_l1 is None or self.grid_current_l2 is None:
            return None
        return round(self.grid_current_l1 + self.grid_current_l2, 2)

    @property
    def grid_connected(self) -> bool | None:
        if self.grid_connected_raw is None:
            return None
        return bool(self.grid_connected_raw & 1)

    @property
    def active_faults(self) -> list[str]:
        """Active fault codes, e.g. ``["F35"]``. Bit n of the 64-bit word is F(n+1)."""
        bits = 0
        for i, word in enumerate(
            (self.fault_word_1, self.fault_word_2, self.fault_word_3, self.fault_word_4)
        ):
            if word is None:
                return []
            bits |= word << (16 * i)
        return [f"F{n + 1:02d}" for n in range(64) if bits >> n & 1]


class Energy(Component):
    """Daily and lifetime energy counters, in kWh."""

    max_span = MAX_SPAN

    day_active_energy = gauge(60, 0.1, unit="kWh")
    total_active_energy = uint32(63, scale=0.1, word_order="little", unit="kWh")
    day_battery_charge = gauge(70, 0.1, signed=False, unit="kWh")
    day_battery_discharge = gauge(71, 0.1, signed=False, unit="kWh")
    total_battery_charge = uint32(72, scale=0.1, word_order="little", unit="kWh")
    total_battery_discharge = uint32(74, scale=0.1, word_order="little", unit="kWh")
    day_grid_import = gauge(76, 0.1, signed=False, unit="kWh")
    day_grid_export = gauge(77, 0.1, signed=False, unit="kWh")
    # Lifetime grid import is split: low word at 78, high word at 80.
    total_grid_import_low = raw_register(78)
    total_grid_import_high = raw_register(80)
    total_grid_export = uint32(81, scale=0.1, word_order="little", unit="kWh")
    day_load_energy = gauge(84, 0.1, signed=False, unit="kWh")
    total_load_energy = uint32(85, scale=0.1, word_order="little", unit="kWh")
    total_pv_energy = uint32(96, scale=0.1, word_order="little", unit="kWh")
    day_pv_energy = gauge(108, 0.1, signed=False, unit="kWh")

    @property
    def total_grid_import(self) -> float | None:
        if self.total_grid_import_low is None or self.total_grid_import_high is None:
            return None
        return round((self.total_grid_import_high << 16 | self.total_grid_import_low) * 0.1, 1)


class SunsynkInverter(Device):
    """A Sunsynk single-phase hybrid inverter on a Modbus unit.

    ``async_update_readings()`` is cheap enough to poll every few seconds;
    ``async_update_energy()`` only needs to run every minute or so.
    """

    def __init__(self, unit: ModbusUnit) -> None:
        super().__init__(unit)
        unit.require_timeout(REQUEST_TIMEOUT)
        self.identity = Identity(unit)
        self.battery_settings = BatterySettings(unit)
        self.readings = Readings(unit)
        self.energy = Energy(unit)

    async def _async_setup(self) -> None:
        await self.identity.async_update()
        # Older firmware may not serve the battery settings. Timeouts and lost
        # connections still raise, so that the caller can retry.
        with contextlib.suppress(ModbusExceptionError):
            await self.battery_settings.async_update()

    @property
    def has_battery(self) -> bool:
        """Whether the inverter is set up to use a battery.

        False only when the battery mode is set to no battery. If the mode is
        unknown, assume a battery so that its values are not hidden.
        """
        return self.battery_settings.battery_mode is not BatteryMode.NO_BATTERY

    async def async_update_readings(self) -> UpdateReport:
        return await self.async_poll(("readings",))

    async def async_update_energy(self) -> UpdateReport:
        return await self.async_poll(("energy",))

    async def async_update(self) -> UpdateReport:
        return await self.async_poll(("readings", "energy"))
