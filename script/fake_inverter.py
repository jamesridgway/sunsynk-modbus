"""Serve a register snapshot over Modbus TCP, for working without an inverter.

python script/fake_inverter.py                       # tests/fixtures/sg01lp1_3k6.json
python script/fake_inverter.py --snapshot other.json --port 5020
python script/query.py 127.0.0.1 --port 5020
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from tmodbus.pdu import ReadHoldingRegistersPDU
from tmodbus.server import AsyncTcpServer, ModbusRequestRouter

DEFAULT_SNAPSHOT = Path(__file__).parent.parent / "tests" / "fixtures" / "sg01lp1_3k6.json"


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    parser.add_argument("--port", type=int, default=5020)
    args = parser.parse_args()

    holding = {int(a): v for a, v in json.loads(args.snapshot.read_text())["holding"].items()}
    router = ModbusRequestRouter()

    @router.register(ReadHoldingRegistersPDU)
    async def read_holding(unit_id: int, request: ReadHoldingRegistersPDU) -> list[int]:
        start = request.start_address
        return [holding.get(a, 0) for a in range(start, start + request.quantity)]

    server = AsyncTcpServer(host="127.0.0.1", port=args.port, handler=router)
    print(f"Serving {args.snapshot.name} on 127.0.0.1:{args.port}")
    await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
