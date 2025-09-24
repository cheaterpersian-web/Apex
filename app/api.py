from __future__ import annotations

from aiohttp import web
from typing import Any, Dict

from .models import CheckResult, CheckStatus
from .storage import JsonStorage


def build_app(storage: JsonStorage, agent_token: str | None) -> web.Application:
    app = web.Application()

    async def health(_request: web.Request) -> web.Response:
        return web.json_response({"status": "ok"})

    async def post_report(request: web.Request) -> web.Response:
        if agent_token:
            auth = request.headers.get("Authorization", "")
            if auth != f"Bearer {agent_token}":
                return web.json_response({"error": "unauthorized"}, status=401)
        payload: Dict[str, Any] = await request.json()
        region = str(payload.get("region", "unknown"))
        items = payload.get("results", [])
        for item in items:
            try:
                result = CheckResult(
                    protocol_id=str(item["protocol_id"]),
                    status=CheckStatus(str(item["status"]).lower()),
                    latency_ms=item.get("latency_ms"),
                    error=item.get("error"),
                )
                await storage.update_region_status(region, result)
            except Exception:
                continue
        return web.json_response({"ok": True})

    app.add_routes([web.get("/health", health), web.post("/report", post_report)])
    return app


async def run_server(storage: JsonStorage, host: str, port: int, agent_token: str | None) -> None:
    app = build_app(storage, agent_token)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host=host, port=port)
    await site.start()
