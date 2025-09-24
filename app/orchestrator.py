from __future__ import annotations

import asyncio
from typing import Dict, List

from .models import ProtocolConfig, CheckResult, CheckStatus
from .storage import JsonStorage
from .checkers import run_protocol_check


class Orchestrator:
    def __init__(self, storage: JsonStorage, check_interval: int, test_url: str, tcp_timeout: int, udp_timeout: int) -> None:
        self.storage = storage
        self.check_interval = check_interval
        self.test_url = test_url
        self.tcp_timeout = tcp_timeout
        self.udp_timeout = udp_timeout
        self._stop_event = asyncio.Event()
        self._listeners: List = []  # callables: (old, new, cfg) -> awaitable

    def subscribe(self, coro_func):
        self._listeners.append(coro_func)

    async def _notify_listeners(self, old: Dict | None, new: Dict, cfg: ProtocolConfig):
        for listener in list(self._listeners):
            try:
                await listener(old, new, cfg)
            except Exception:  # noqa: BLE001
                # Do not crash orchestrator on listener error
                continue

    async def run_once(self) -> None:
        protocols = await self.storage.list_protocols()
        current_status = await self.storage.get_status()

        async def check_and_update(cfg: ProtocolConfig):
            result = await run_protocol_check(cfg, self.test_url, self.tcp_timeout, self.udp_timeout)
            old = current_status.get(cfg.id)
            new = {
                "protocol_id": result.protocol_id,
                "status": result.status.value,
                "latency_ms": result.latency_ms,
                "timestamp_iso": result.timestamp_iso,
                "error": result.error,
            }
            await self.storage.update_status(result)
            # Notify only on transitions to CONNECTED
            if (old is None or old.get("status") != new["status"]) and new["status"] == CheckStatus.CONNECTED.value:
                await self._notify_listeners(old, new, cfg)

        # Run checks concurrently
        await asyncio.gather(*(check_and_update(cfg) for cfg in protocols))

    async def run_forever(self) -> None:
        while not self._stop_event.is_set():
            try:
                await self.run_once()
            except Exception:  # noqa: BLE001
                pass
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self.check_interval)
            except asyncio.TimeoutError:
                continue

    def stop(self) -> None:
        self._stop_event.set()