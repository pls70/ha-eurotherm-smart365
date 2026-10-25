"""A fake SmartComfort 365 speaking Modbus TCP, for tests."""

from __future__ import annotations

import asyncio
import struct


def default_registers() -> dict[int, int]:
    """Registers of a panel with one zone, one module and six rooms."""
    regs = {50: 0x0001, 51: 0x0002, 58: 120, 59: 1}
    regs.update({100: 0, 101: 1, 102: 0, 103: 0, 104: 1, 105: 0b1})
    regs.update({1140: 0, 1141: 0, 1142: 6, 1143: 0, 1144: 0, 1145: 300, 1146: 285})
    temps = [190, 200, 200, 195, 195, 195]
    for room in range(8):
        base = 1200 + 400 * room
        if room < 6:
            regs.update(
                {
                    base: room, base + 1: 0, base + 2: 0, base + 3: 1, base + 4: 0,
                    base + 5: temps[room], base + 6: 0, base + 7: 0, base + 8: 200,
                    base + 9: 1, base + 10: 210,
                }
            )
        else:
            regs.update({base + i: 0 for i in range(11)})
    return regs


class FakeSmart365:
    """Serves FC03/FC06 over TCP from a register dict."""

    def __init__(self, registers: dict[int, int] | None = None) -> None:
        self.registers = registers if registers is not None else default_registers()
        self.writes: list[tuple[int, int]] = []
        self.server: asyncio.base_events.Server | None = None
        self.port = 0

    async def start(self) -> None:
        self.server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        self.port = self.server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        assert self.server is not None
        self.server.close()
        self.server.close_clients()
        await self.server.wait_closed()

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            while True:
                tid, pid, length, unit = struct.unpack(">HHHB", await reader.readexactly(7))
                pdu = await reader.readexactly(length - 1)
                writer.write(self._reply(tid, pid, unit, pdu))
                await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError):
            writer.close()

    def _reply(self, tid: int, pid: int, unit: int, pdu: bytes) -> bytes:
        fc = pdu[0]
        if fc == 0x03:
            address, count = struct.unpack(">HH", pdu[1:5])
            if any(a not in self.registers for a in range(address, address + count)):
                body = bytes([0x83, 0x02])
            else:
                values = [self.registers[a] for a in range(address, address + count)]
                body = bytes([0x03, count * 2]) + struct.pack(f">{count}H", *values)
        elif fc == 0x06:
            address, value = struct.unpack(">HH", pdu[1:5])
            self.registers[address] = value
            self.writes.append((address, value))
            body = pdu
        else:
            body = bytes([fc | 0x80, 0x01])
        return struct.pack(">HHHB", tid, pid, len(body) + 1, unit) + body
