# sunsynk-modbus

Read Sunsynk single-phase hybrid inverters (SG01LP1 family: 3.6, 5 and 8 kW) over Modbus.

The library is built on [`modbus-connection`](https://github.com/home-assistant-libs/modbus-connection)'s
device-modelling framework, the same foundation as Home Assistant's Modbus device integrations.
It holds the inverter's register map and decoding only. The caller owns the connection, so you can
reach the inverter however suits you:
- a Modbus TCP gateway on the inverter's RS485 port, such as an ESP32 or a USR-style adapter;
- a USB RS485 adapter;
- RTU over TCP.

## Install

```bash
pip install "sunsynk-modbus[tmodbus]"
```

## Usage

```python
import asyncio

from modbus_connection import ModbusTcpParams
from modbus_connection.tmodbus import ModbusConnection
from sunsynk_modbus import SunsynkInverter


async def main() -> None:
    conn = ModbusConnection(ModbusTcpParams(host="192.168.1.50"))
    inverter = SunsynkInverter(conn.for_unit(1))  # unit = the inverter's "Modbus SN"
    try:
        await inverter.async_update()
        print(inverter.identity.serial_number)
        print(inverter.readings.pv_power, inverter.readings.battery_soc)
        print(inverter.energy.total_grid_import)
    finally:
        await conn.close()


asyncio.run(main())
```

What each poll reads:
- **`async_update_readings()`:** live power, voltage, current, temperature, state and fault values. Cheap enough to run every few seconds.
- **`async_update_energy()`:** the daily and lifetime kWh counters.
- **`async_update()`:** both.

The identity (serial number and rated power) is read once, on the first poll.

### Sign conventions

These were checked on a 3.6K-SG01LP1:

| Value | Positive | Negative |
|---|---|---|
| `battery_power`, `battery_current` | discharging | charging |
| `grid_power`, `grid_ct_power` | importing | exporting |

### Inverter settings

- **Port settings:** the RS485 port runs at 9600 baud, 8N1.
- **Unit ID:** set *Settings → Advanced → Multi-Inverter → Modbus SN* to the unit ID you poll, usually `01`.
- **After a firmware update:** a firmware update can reset Modbus SN to `00`. At `00` the inverter doesn't respond at all.

## Scripts

```bash
python script/query.py 192.168.1.50                 # print every value
python script/query.py 192.168.1.50 --watch 5       # live power readings
python script/query.py 192.168.1.50 --raw 150 45    # dump raw registers
python script/fake_inverter.py                      # serve the test fixture on 127.0.0.1:5020
```

## Development

```bash
python -m venv .venv && .venv/bin/pip install -e . --group dev
.venv/bin/ruff check . && .venv/bin/mypy && .venv/bin/pytest
```

`tests/fixtures/sg01lp1_3k6.json` is a register snapshot from a real 3.6 kW inverter, with the
serial number replaced.

## Credits

The register map follows [kellerza/sunsynk](https://github.com/kellerza/sunsynk)'s single-phase definitions.
