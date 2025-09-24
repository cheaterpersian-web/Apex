from __future__ import annotations

import json
from typing import Callable, Awaitable, Optional

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, ApplicationBuilder, CommandHandler, ContextTypes

from .models import protocol_config_from_dict, protocol_config_to_dict, ProtocolConfig
from .storage import JsonStorage
from .utils import format_latency


def build_app(token: str, post_init: Optional[Callable[[Application], Awaitable[None]]] = None) -> Application:
    builder = ApplicationBuilder().token(token)
    if post_init is not None:
        builder = builder.post_init(post_init)
    return builder.build()


def _help_text() -> str:
    return (
        "This bot monitors VPN/proxy protocols and notifies when they are reachable.\n\n"
        "Commands:\n"
        "/status - Show current status of all protocols\n"
        "/refresh - Trigger an immediate re-check\n"
        "/subscribe - Receive notifications when a protocol becomes CONNECTED\n"
        "/unsubscribe - Stop receiving notifications\n"
        "/list_protocols - List protocols\n"
        "/add_protocol <json> - Add or replace a protocol\n"
        "/remove_protocol <id> - Remove a protocol by id\n"
    )


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(_help_text())


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(_help_text())


async def cmd_status(storage: JsonStorage, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    protocols = await storage.list_protocols()
    status = await storage.get_status()
    if not protocols:
        await update.message.reply_text("No protocols configured. Use /add_protocol <json>.")
        return

    connected_lines: list[str] = []
    disconnected_lines: list[str] = []
    error_lines: list[str] = []

    def fmt_line(icon: str, cfg: ProtocolConfig, lat: str, ts: str, err: str | None) -> str:
        base = f"{icon} <b>{cfg.name}</b> <code>({cfg.type.value})</code> • {lat} • {ts}"
        if err:
            short_err = (err[:140] + "…") if len(err) > 140 else err
            return base + f"\n<i>error: {short_err}</i>"
        return base

    for cfg in protocols:
        s = status.get(cfg.id)
        state: str = (s.get("status") if s else "unknown").lower()
        lat = format_latency(s.get("latency_ms") if s else None)
        ts = s.get("timestamp_iso") if s else "-"
        err = s.get("error") if s else None

        if state == "connected":
            connected_lines.append(fmt_line("✅", cfg, lat, ts, None))
        elif state == "disconnected":
            disconnected_lines.append(fmt_line("❌", cfg, lat, ts, err))
        else:
            error_lines.append(fmt_line("⚠️", cfg, lat, ts, err))

    total = len(protocols)
    n_conn = len(connected_lines)
    n_disc = len(disconnected_lines)
    n_err = len(error_lines)

    lines: list[str] = [
        f"<b>Protocol Status</b> — total: {total} | connected: {n_conn} | disconnected: {n_disc} | error: {n_err}",
    ]
    if connected_lines:
        lines.append("\n<b>Connected</b>:")
        lines.extend(connected_lines)
    if disconnected_lines:
        lines.append("\n<b>Disconnected</b>:")
        lines.extend(disconnected_lines)
    if error_lines:
        lines.append("\n<b>Errors</b>:")
        lines.extend(error_lines)

    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


async def cmd_refresh(orchestrator_run_once: Callable[[], Awaitable[None]], update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Refreshing...")
    await orchestrator_run_once()
    await update.message.reply_text("Done.")


async def cmd_subscribe(storage: JsonStorage, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    await storage.add_subscriber(user_id)
    await update.message.reply_text("Subscribed to notifications.")


async def cmd_unsubscribe(storage: JsonStorage, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    removed = await storage.remove_subscriber(user_id)
    await update.message.reply_text("Unsubscribed." if removed else "You were not subscribed.")


async def cmd_list_protocols(storage: JsonStorage, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    protocols = await storage.list_protocols()
    if not protocols:
        await update.message.reply_text("No protocols configured.")
        return
    lines = ["Configured Protocols:"]
    for cfg in protocols:
        lines.append(f"• {cfg.id}: {cfg.name} ({cfg.type.value}) {cfg.transport.value}")
    await update.message.reply_text("\n".join(lines))


async def cmd_add_protocol(storage: JsonStorage, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Usage: /add_protocol {json}")
        return
    raw = " ".join(context.args)
    try:
        data = json.loads(raw)
        cfg: ProtocolConfig = protocol_config_from_dict(data)
        await storage.add_protocol(cfg)
        await update.message.reply_text(f"Added/updated: {cfg.id}")
    except Exception as exc:  # noqa: BLE001
        await update.message.reply_text(f"Error: {exc}")


async def cmd_remove_protocol(storage: JsonStorage, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Usage: /remove_protocol <id>")
        return
    pid = context.args[0]
    removed = await storage.remove_protocol(pid)
    await update.message.reply_text("Removed." if removed else "Not found.")


def register_handlers(app: Application, storage: JsonStorage, orchestrator_run_once: Callable[[], Awaitable[None]]):
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("status", lambda u, c: cmd_status(storage, u, c)))
    app.add_handler(CommandHandler("refresh", lambda u, c: cmd_refresh(orchestrator_run_once, u, c)))
    app.add_handler(CommandHandler("subscribe", lambda u, c: cmd_subscribe(storage, u, c)))
    app.add_handler(CommandHandler("unsubscribe", lambda u, c: cmd_unsubscribe(storage, u, c)))
    app.add_handler(CommandHandler("list_protocols", lambda u, c: cmd_list_protocols(storage, u, c)))
    app.add_handler(CommandHandler("add_protocol", lambda u, c: cmd_add_protocol(storage, u, c)))
    app.add_handler(CommandHandler("remove_protocol", lambda u, c: cmd_remove_protocol(storage, u, c)))