from __future__ import annotations

import logging
import asyncio

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

    # Schedule periodic checks via post_init so job_queue is available
    async def post_init(application):
        async def job_run_once(_):
            await orchestrator.run_once()
        jq = getattr(application, "job_queue", None)
        if jq is None:
            logging.warning("JobQueue is not available. Falling back to asyncio task. To enable JobQueue, install python-telegram-bot with the job-queue extra.")

            async def periodic_checker():
                await asyncio.sleep(3)
                while True:
                    try:
                        await orchestrator.run_once()
                    except Exception as exc:  # noqa: BLE001
                        logging.exception("Periodic check failed: %s", exc)
                    await asyncio.sleep(cfg.check_interval_seconds)

            # Bind task to application's lifecycle if available
            try:
                application.create_task(periodic_checker())
            except Exception:  # noqa: BLE001
                asyncio.get_running_loop().create_task(periodic_checker())
            return
        jq.run_repeating(job_run_once, interval=cfg.check_interval_seconds, first=3)

    app = build_app(cfg.telegram_bot_token, post_init=post_init)

    # Wire bot commands
    register_handlers(app, storage, orchestrator.run_once)

    # Notifications on transition to CONNECTED
    orchestrator.subscribe(notify_handler_factory(app, storage))

    # Periodic job scheduled in post_init above

    # Start polling (blocks until interrupted)
    app.run_polling(close_loop=False)


if __name__ == "__main__":
    main()