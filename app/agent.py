from __future__ import annotations

import asyncio
import json
import os
from typing import Any, Dict, List

import aiohttp

from .settings import load_config
from .storage import JsonStorage
from .checkers import run_protocol_check


async def main() -> None:
    # This agent is intended to run on a machine in Iran. It loads the same storage (protocols.json)
    # and performs checks locally, then POSTs summarized results back to the central server.
    cfg = load_config()
    region = os.getenv("AGENT_REGION", "iran")
    server_base = os.getenv("AGENT_SERVER", f"http://127.0.0.1:{cfg.agent_api_port}")
    token = os.getenv("AGENT_TOKEN", cfg.agent_token or "")

    storage = JsonStorage(cfg.storage_dir)
    protocols = await storage.list_protocols()

    results: List[Dict[str, Any]] = []
    for p in protocols:
        try:
            result = await run_protocol_check(p, cfg.proxy_test_url, cfg.tcp_timeout_seconds, cfg.udp_timeout_seconds)
            results.append({
                "protocol_id": result.protocol_id,
                "status": result.status.value,
                "latency_ms": result.latency_ms,
                "timestamp_iso": result.timestamp_iso,
                "error": result.error,
            })
        except Exception as exc:  # noqa: BLE001
            results.append({
                "protocol_id": p.id,
                "status": "error",
                "latency_ms": None,
                "timestamp_iso": None,
                "error": str(exc),
            })

    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{server_base}/report", data=json.dumps({
            "region": region,
            "results": results,
        }), headers=headers) as resp:
            text = await resp.text()
            if resp.status >= 300:
                raise SystemExit(f"report failed: {resp.status} {text}")
            print(text)


if __name__ == "__main__":
    asyncio.run(main())

