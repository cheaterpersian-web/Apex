from __future__ import annotations

import logging

from .settings import load_config
from .storage import JsonStorage
from .orchestrator import Orchestrator
from .bot import build_app, register_handlers


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def notify_handler_factory(app, storage: JsonStorage):
    async def _handler(old, new, cfg):
        subs = await storage.list_subscribers()
        if not subs:
            return
        text = (
            f"✅ {cfg.name} ({cfg.type.value}) is CONNECTED\n"
            f"Host: {cfg.host}:{cfg.port}/{cfg.transport.value}\n"
            f"Latency: {new.get('latency_ms', '-') } ms\n"
            f"Time: {new.get('timestamp_iso', '-') }"
        )
        for sub in subs:
            try:
                await app.bot.send_message(chat_id=sub.user_id, text=text)
            except Exception:  # noqa: BLE001
                continue
    return _handler


def main():
    try:
        import uvloop  # type: ignore
        uvloop.install()
    except Exception:  # noqa: BLE001
        pass

    cfg = load_config()
    if not cfg.telegram_bot_token:
        raise SystemExit("TELEGRAM_BOT_TOKEN is not set in environment or .env")

    storage = JsonStorage(cfg.storage_dir)
    orchestrator = Orchestrator(
        storage,
        cfg.check_interval_seconds,
        cfg.proxy_test_url,
        cfg.tcp_timeout_seconds,
        cfg.udp_timeout_seconds,
    )

    app = build_app(cfg.telegram_bot_token)

    # Wire bot commands
    register_handlers(app, storage, orchestrator.run_once)

    # Notifications on transition to CONNECTED
    orchestrator.subscribe(notify_handler_factory(app, storage))

    # Schedule periodic checks via JobQueue
    async def job_run_once(_):
        await orchestrator.run_once()

    app.job_queue.run_repeating(job_run_once, interval=cfg.check_interval_seconds, first=3)

    # Start polling (blocks until interrupted)
    app.run_polling(close_loop=False)


if __name__ == "__main__":
    main()