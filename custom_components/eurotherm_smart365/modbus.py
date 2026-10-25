"""Minimal asyncio Modbus TCP client for the SmartComfort 365.

The device only needs function codes 0x03 (read holding registers) and
0x06 (write single register), so we speak the protocol directly instead of
depending on a specific pymodbus version.
"""

from __future__ import annotations

import asyncio
import logging
import struct

_LOGGER = logging.getLogger(__name__)

FC_READ_HOLDING = 0x03
FC_WRITE_SINGLE = 0x06
MAX_READ_COUNT = 125


class Smart365Error(Exception):
    """Communication error with the SmartComfort 365."""


class Smart365ModbusException(Smart365Error):
    """The device answered with a Modbus exception code."""

    def __init__(self, function: int, code: int) -> None:
        super().__init__(f"Modbus exception {code} for function {function:#04x}")
        self.code = code


class Smart365Client:
    """Keeps one TCP connection open, as the Eurotherm manual recommends."""

    def __init__(self, host: str, port: int, unit_id: int, timeout: float = 5.0) -> None:
        self.host = host
        self.port = port
        self.unit_id = unit_id
        self.timeout = timeout
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._lock = asyncio.Lock()
        self._transaction_id = 0

    async def close(self) -> None:
        """Close the connection."""
        async with self._lock:
            await self._close()

    async def _close(self) -> None:
        writer = self._writer
        self._reader = self._writer = None
        if writer is not None:
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass

    async def _connect(self) -> None:
        if self._writer is not None and not self._writer.is_closing():
            return
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port), self.timeout
            )
        except (OSError, TimeoutError) as err:
            raise Smart365Error(f"Cannot connect to {self.host}:{self.port}: {err}") from err

    async def _transact(self, pdu: bytes) -> bytes:
        self._transaction_id = (self._transaction_id + 1) & 0xFFFF
        tid = self._transaction_id
        frame = struct.pack(">HHHB", tid, 0, len(pdu) + 1, self.unit_id) + pdu
        assert self._writer is not None and self._reader is not None
        self._writer.write(frame)
        await self._writer.drain()
        while True:
            header = await self._reader.readexactly(7)
            rtid, _pid, length, _unit = struct.unpack(">HHHB", header)
            body = await self._reader.readexactly(length - 1)
            if rtid == tid:
                break
            _LOGGER.debug("Discarding stale Modbus response %s (expected %s)", rtid, tid)
        if body[0] & 0x80:
            raise Smart365ModbusException(body[0] & 0x7F, body[1])
        if body[0] != pdu[0]:
            raise Smart365Error(f"Unexpected function code {body[0]:#04x}")
        return body

    async def _request(self, pdu: bytes) -> bytes:
        async with self._lock:
            for attempt in (1, 2):
                await self._connect()
                try:
                    return await asyncio.wait_for(self._transact(pdu), self.timeout)
                except Smart365ModbusException:
                    raise
                except (OSError, TimeoutError, asyncio.IncompleteReadError, Smart365Error) as err:
                    # The device may close idle connections: reconnect once.
                    await self._close()
                    if attempt == 2:
                        raise Smart365Error(f"Modbus request failed: {err}") from err
        raise Smart365Error("unreachable")

    async def read_registers(self, address: int, count: int) -> list[int]:
        """Read `count` holding registers starting at `address`."""
        if not 1 <= count <= MAX_READ_COUNT:
            raise ValueError(f"count must be between 1 and {MAX_READ_COUNT}")
        body = await self._request(struct.pack(">BHH", FC_READ_HOLDING, address, count))
        byte_count = body[1]
        if byte_count != count * 2 or len(body) < 2 + byte_count:
            raise Smart365Error("Malformed read response")
        return list(struct.unpack(f">{count}H", body[2 : 2 + byte_count]))

    async def write_register(self, address: int, value: int) -> None:
        """Write a single holding register."""
        await self._request(struct.pack(">BHH", FC_WRITE_SINGLE, address, value & 0xFFFF))
