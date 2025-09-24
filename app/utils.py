from __future__ import annotations

import asyncio
import re
import socket
import time
from contextlib import closing
from typing import Optional, Tuple


def utc_iso_now() -> str:
    import datetime as _dt
    return _dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"


async def tcp_connect_latency(host: str, port: int, timeout: int) -> Tuple[bool, Optional[int], Optional[str]]:
    start = time.perf_counter()
    try:
        fut = asyncio.open_connection(host, port)
        reader, writer = await asyncio.wait_for(fut, timeout=timeout)
        writer.close()
        with contextlib_suppress(asyncio.CancelledError):
            await writer.wait_closed()
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        return True, elapsed_ms, None
    except Exception as exc:  # noqa: BLE001
        return False, None, str(exc)


async def udp_probe(host: str, port: int, timeout: int) -> Tuple[bool, Optional[int], Optional[str]]:
    # Best-effort UDP probe: send a dummy packet and wait briefly for any response.
    start = time.perf_counter()
    try:
        loop = asyncio.get_running_loop()
        with closing(socket.socket(socket.AF_INET, socket.SOCK_DGRAM)) as sock:
            sock.setblocking(False)
            sock.sendto(b"ping", (host, port))
            # Wait for readability or timeout
            fut = loop.sock_recv(sock, 1)
            try:
                await asyncio.wait_for(fut, timeout=timeout)
            except asyncio.TimeoutError:
                # UDP often has no response. Treat send success as "reachable" best-effort.
                pass
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        return True, elapsed_ms, None
    except Exception as exc:  # noqa: BLE001
        return False, None, str(exc)


class contextlib_suppress:
    def __init__(self, *exceptions):
        self._exceptions = exceptions

    def __enter__(self):
        return None

    def __exit__(self, exc_type, exc, tb):
        return exc_type is not None and issubclass(exc_type, self._exceptions)


async def wait_for_regex(stream: asyncio.StreamReader, pattern: str, timeout: int) -> bool:
    regex = re.compile(pattern)
    end_time = time.time() + timeout
    buffer = b""
    while time.time() < end_time:
        try:
            chunk = await asyncio.wait_for(stream.read(1024), timeout=0.2)
        except asyncio.TimeoutError:
            chunk = b""
        if not chunk:
            await asyncio.sleep(0.1)
            continue
        buffer += chunk
        if regex.search(buffer.decode(errors="ignore")):
            return True
    return False


def format_latency(latency_ms: Optional[int]) -> str:
    if latency_ms is None:
        return "-"
    return f"{latency_ms} ms"