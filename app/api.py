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

    async def ws_echo(request: web.Request) -> web.StreamResponse:
        ws = web.WebSocketResponse(heartbeat=20)
        await ws.prepare(request)
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                if msg.data == "ping":
                    await ws.send_str("pong")
                else:
                    await ws.send_str(msg.data)
            elif msg.type == web.WSMsgType.BINARY:
                await ws.send_bytes(msg.data)
            elif msg.type == web.WSMsgType.ERROR:
                break
        return ws

    async def serve_client(_request: web.Request) -> web.Response:
        # Minimal embedded client for browser-based probing
        html = """
<!doctype html>
<html>
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Connectivity Probe</title>
  <style>
    body { font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; padding: 16px; }
    .ok { color: #0a8; }
    .bad { color: #c22; }
    code { background:#f3f3f3; padding: 2px 4px; border-radius: 4px; }
  </style>
}</head>
<body>
  <h2>Connectivity Probe</h2>
  <div id=\"log\"></div>
  <script>
    const log = (html) => { document.getElementById('log').insertAdjacentHTML('beforeend', html + '<br/>'); };
    const origin = window.location.origin;

    const results = [];
    const add = (id, ok, latency, error) => {
      results.push({ id, ok, latency, error: error ? String(error) : null });
      const cls = ok ? 'ok' : 'bad';
      const lat = (latency !== null && latency !== undefined) ? (latency + ' ms') : '-';
      log(`<span class=\"${cls}\">${ok ? '✅' : '❌'}</span> <b>${id}</b> — <code>${lat}</code>${error ? ' — ' + error : ''}`);
    };

    const measure = async (fn) => {
      const t0 = performance.now();
      try {
        const val = await fn();
        const dt = Math.round(performance.now() - t0);
        return [true, dt, val];
      } catch (e) {
        return [false, null, e];
      }
    };

    (async () => {
      // Same-origin API health (HTTP)
      {
        const [ok, dt, e] = await measure(() => fetch(origin + '/health', { cache: 'no-store' }));
        add('api_http_health', ok, dt, ok ? null : e);
      }

      // WebSocket echo
      {
        const [ok, dt, e] = await measure(() => new Promise((resolve, reject) => {
          const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
          const ws = new WebSocket(proto + '://' + window.location.host + '/ws');
          let openedAt = 0;
          ws.onopen = () => { openedAt = performance.now(); ws.send('ping'); };
          ws.onmessage = (ev) => { try { ws.close(); } catch(_){}; resolve('ok'); };
          ws.onerror = (ev) => reject('ws error');
          ws.onclose = () => {};
        }));
        add('api_websocket_echo', ok, dt, ok ? null : e);
      }

      // Public internet reachability via image loads (no CORS issues)
      const imgTest = (url) => new Promise((resolve, reject) => { const i = new Image(); i.onload = () => resolve('ok'); i.onerror = () => reject('error'); i.src = url + '?cachebust=' + Math.random(); });
      {
        const [ok, dt, e] = await measure(() => imgTest('https://www.google.com/favicon.ico'));
        add('internet_google', ok, dt, ok ? null : e);
      }
      {
        const [ok, dt, e] = await measure(() => imgTest('https://www.cloudflare.com/favicon.ico'));
        add('internet_cloudflare', ok, dt, ok ? null : e);
      }
      {
        const [ok, dt, e] = await measure(() => imgTest('https://upload.wikimedia.org/wikipedia/commons/6/63/Wikipedia-logo.png'));
        add('internet_wikipedia', ok, dt, ok ? null : e);
      }

      // Auto-report back to server under region=iran-web
      try {
        const payload = { region: 'iran-web', results: results.map(r => ({
          protocol_id: r.id,
          status: r.ok ? 'connected' : 'disconnected',
          latency_ms: r.latency,
          error: r.error
        }))};
        await fetch(origin + '/report', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
        log('<hr><b>Results reported to server.</b> Now check /status in your bot.');
      } catch (e) {
        log('<hr><b>Failed to report results.</b>');
      }
    })();
  </script>
</body>
</html>
        """
        return web.Response(text=html, content_type="text/html")

    app.add_routes([
        web.get("/health", health),
        web.post("/report", post_report),
        web.get("/ws", ws_echo),
        web.get("/client", serve_client),
    ])
    return app


async def run_server(storage: JsonStorage, host: str, port: int, agent_token: str | None) -> None:
    app = build_app(storage, agent_token)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host=host, port=port)
    await site.start()
