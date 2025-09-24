from __future__ import annotations

import asyncio
import os
import signal
import time
from typing import Optional, Tuple

from .models import ProtocolConfig, ProtocolType, TransportType, CheckResult, CheckStatus
from .utils import tcp_connect_latency, udp_probe, wait_for_regex


class ClientProcess:
    def __init__(self, command: str, ready_regex: Optional[str], startup_timeout: int) -> None:
        self.command = command
        self.ready_regex = ready_regex
        self.startup_timeout = startup_timeout
        self.proc: Optional[asyncio.subprocess.Process] = None

    async def __aenter__(self):
        # Shell execution for user-provided commands. User is responsible for safety.
        self.proc = await asyncio.create_subprocess_shell(
            self.command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        if self.ready_regex and self.proc.stdout:
            ready = await wait_for_regex(self.proc.stdout, self.ready_regex, self.startup_timeout)
            if not ready:
                await self._terminate()
                raise RuntimeError("Client did not become ready in time")
        else:
            # No readiness check; just give it a small head start
            await asyncio.sleep(min(2, self.startup_timeout))
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self._terminate()

    async def _terminate(self):
        if not self.proc:
            return
        proc = self.proc
        if proc.returncode is None:
            try:
                proc.send_signal(signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(proc.wait(), timeout=5)
            except asyncio.TimeoutError:
                with contextlib_suppress(Exception):
                    proc.kill()
                    await proc.wait()


class contextlib_suppress:
    def __init__(self, *exceptions):
        self._exceptions = exceptions

    def __enter__(self):
        return None

    def __exit__(self, exc_type, exc, tb):
        return exc_type is not None and issubclass(exc_type, self._exceptions)


async def check_basic_connectivity(cfg: ProtocolConfig, tcp_timeout: int, udp_timeout: int) -> Tuple[CheckStatus, Optional[int], Optional[str]]:
    if cfg.transport == TransportType.TCP:
        ok, latency, err = await tcp_connect_latency(cfg.host, cfg.port, tcp_timeout)
        return (CheckStatus.CONNECTED if ok else CheckStatus.DISCONNECTED), latency, err
    else:
        ok, latency, err = await udp_probe(cfg.host, cfg.port, udp_timeout)
        return (CheckStatus.CONNECTED if ok else CheckStatus.DISCONNECTED), latency, err


async def check_via_client_proxy(cfg: ProtocolConfig, test_url: str, tcp_timeout: int) -> Tuple[CheckStatus, Optional[int], Optional[str]]:
    # Start client, then do HTTP GET via SOCKS proxy using aiohttp-socks
    assert cfg.client is not None and cfg.client.socks_port is not None
    from aiohttp import ClientSession
    from aiohttp_socks import ProxyConnector

    start = time.perf_counter()
    try:
        async with ClientProcess(cfg.client.start_command, cfg.client.ready_regex, cfg.client.startup_timeout_sec):
            connector = ProxyConnector.from_url(f"socks5://127.0.0.1:{cfg.client.socks_port}")
            timeout = aiohttp_timeout(total=tcp_timeout)
            async with ClientSession(connector=connector, timeout=timeout) as session:
                async with session.get(test_url) as resp:
                    if resp.status in (200, 204):
                        latency_ms = int((time.perf_counter() - start) * 1000)
                        return CheckStatus.CONNECTED, latency_ms, None
                    else:
                        return CheckStatus.DISCONNECTED, None, f"HTTP {resp.status}"
    except Exception as exc:  # noqa: BLE001
        return CheckStatus.ERROR, None, str(exc)


def aiohttp_timeout(total: int):
    # Delayed import to keep optional dependency compatible
    import aiohttp
    return aiohttp.ClientTimeout(total=total)


async def run_protocol_check(cfg: ProtocolConfig, test_url: str, tcp_timeout: int, udp_timeout: int) -> CheckResult:
    # If client is provided and SOCKS port is known, prefer proxy validation
    if cfg.client and cfg.client.socks_port:
        status, latency, err = await check_via_client_proxy(cfg, test_url, tcp_timeout)
        if status == CheckStatus.CONNECTED:
            return CheckResult(protocol_id=cfg.id, status=status, latency_ms=latency)
        # If client route failed to start, fall back to basic connectivity
    status, latency, err = await check_basic_connectivity(cfg, tcp_timeout, udp_timeout)
    return CheckResult(protocol_id=cfg.id, status=status, latency_ms=latency, error=err)