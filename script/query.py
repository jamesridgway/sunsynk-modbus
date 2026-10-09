"""Read a Sunsynk inverter through the Modbus TCP gateway and print every value.

python script/query.py sunsynk-gw.local
python script/query.py 192.168.1.50 --watch 5
python script/query.py 192.168.1.50 --raw 150 45     # dump raw registers
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import time

from modbus_connection import ModbusTcpParams
from modbus_connection.model import Component
from modbus_connection.tmodbus import ModbusConnection

from sunsynk_modbus import SunsynkInverter

EXTRA = {
    "readings": ("pv_power", "grid_current", "grid_connected", "active_faults"),
    "energy": ("total_grid_import",),
}


def print_component(title: str, component: Component, extra: tuple[str, ...] = ()) -> None:
    print(f"\n== {title} ==")
    for name, field in component.declared_fields.items():
        if name.endswith(("_raw", "_low", "_high")) or name.startswith("fault_word"):
            continue
        value = getattr(component, name)
        if hasattr(value, "name"):
            value = value.name
        unit = getattr(field, "unit", None) or ""
        print(f"  {name:32} {value} {unit}")
    for name in extra:
        print(f"  {name:32} {getattr(component, name)}")


async def dump_raw(conn: ModbusConnection, unit_id: int, start: int, count: int) -> None:
    words = await conn.for_unit(unit_id).read_holding_registers(start, count)
    for offset, word in enumerate(words):
        signed = word - 0x10000 if word & 0x8000 else word
        print(f"  {start + offset:5}  0x{word:04x}  {word:6}  {signed:6}")


async def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("host")
    parser.add_argument("--port", type=int, default=502)
    parser.add_argument("--unit", type=int, default=1, help="Modbus unit ID on the gateway")
    parser.add_argument("--watch", type=float, metavar="SECONDS", help="poll readings repeatedly")
    parser.add_argument("--raw", type=int, nargs=2, metavar=("START", "COUNT"))
    args = parser.parse_args()

    conn = ModbusConnection(ModbusTcpParams(host=args.host, port=args.port))
    try:
        if args.raw:
            await dump_raw(conn, args.unit, *args.raw)
            return

        inverter = SunsynkInverter(conn.for_unit(args.unit))
        started = time.monotonic()
        report = await inverter.async_update()
        print(f"Polled in {time.monotonic() - started:.2f}s; failed: {report.failed or 'none'}")
        print_component("Identity", inverter.identity)
        print_component("Readings", inverter.readings, EXTRA["readings"])
        print_component("Energy", inverter.energy, EXTRA["energy"])

        while args.watch:
            await asyncio.sleep(args.watch)
            await inverter.async_update_readings()
            r = inverter.readings
            print(
                f"{time.strftime('%H:%M:%S')}  pv {r.pv_power} W  grid {r.grid_ct_power} W  "
                f"load {r.load_power} W  batt {r.battery_power} W @ {r.battery_soc}%"
            )
    finally:
        await conn.close()


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main())
