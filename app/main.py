from __future__ import annotations

import logging
import asyncio
import os
import socket

from .settings import load_config
from .storage import JsonStorage
from .orchestrator import Orchestrator
from .bot import build_app, register_handlers
from .api import run_server as run_agent_api
from .models import ProtocolConfig, ProtocolType, TransportType


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def notify_handler_factory(app, storage: JsonStorage):
    async def _handler(old, new, cfg):
        subs = await storage.list_subscribers()
        if not subs:
            return
        text = (
            f"✅ {cfg.name} ({cfg.type.value}) is CONNECTED\n"
            f"Transport: {cfg.transport.value}\n"
            f"Latency: {new.get('latency_ms', '-') } ms\n"
            f"Time: {new.get('timestamp_iso', '-') }"
        )
        for sub in subs:
            try:
                await app.bot.send_message(chat_id=sub.user_id, text=text)
            except Exception:  # noqa: BLE001
                continue
    return _handler


def _detect_server_host() -> str:
    env_host = os.getenv("SERVER_HOST") or os.getenv("DEFAULT_HOST")
    if env_host:
        return env_host.strip()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("1.1.1.1", 80))
            return s.getsockname()[0]
    except Exception:  # noqa: BLE001
        return "127.0.0.1"


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
        # Ensure default protocols exist (always ensure/update by id)
        host = _detect_server_host()
        demo = str(os.getenv("DEMO_CONNECTIVITY", "")).lower() in {"1", "true", "yes", "on"}
        public_tcp_host = os.getenv("DEMO_TCP_HOST", "www.google.com")
        public_udp_host = os.getenv("DEMO_UDP_HOST", "1.1.1.1")
        defaults = [
            ProtocolConfig(
                id="openvpn-default",
                name="OpenVPN UDP",
                type=ProtocolType.OPENVPN,
                host=(public_udp_host if demo else host),
                port=(53 if demo else 1194),
                transport=TransportType.UDP,
            ),
            ProtocolConfig(
                id="wireguard-default",
                name="WireGuard UDP",
                type=ProtocolType.WIREGUARD,
                host=(public_udp_host if demo else host),
                port=(53 if demo else 51820),
                transport=TransportType.UDP,
            ),
            ProtocolConfig(
                id="shadowsocks-default",
                name="Shadowsocks TCP",
                type=ProtocolType.SHADOWSOCKS,
                host=(public_tcp_host if demo else host),
                port=(443 if demo else 8388),
                transport=TransportType.TCP,
            ),
            ProtocolConfig(
                id="shadowsocksr-default",
                name="ShadowsocksR TCP",
                type=ProtocolType.SHADOWSOCKSR,
                host=(public_tcp_host if demo else host),
                port=(443 if demo else 8389),
                transport=TransportType.TCP,
            ),
            ProtocolConfig(
                id="v2ray-tcp-default",
                name="V2Ray TCP (VLESS TLS)",
                type=ProtocolType.V2RAY,
                host=(public_tcp_host if demo else host),
                port=443,
                transport=TransportType.TCP,
                meta={"protocol": "vless", "security": "tls"},
            ),
            ProtocolConfig(
                id="v2ray-grpc-default",
                name="V2Ray gRPC (VLESS TLS)",
                type=ProtocolType.V2RAY,
                host=(public_tcp_host if demo else host),
                port=443,
                transport=TransportType.TCP,
                meta={"protocol": "vless", "network": "grpc", "serviceName": "grpc", "security": "tls"},
            ),
            ProtocolConfig(
                id="vmess-default",
                name="VMess TCP",
                type=ProtocolType.VMESS,
                host=(public_tcp_host if demo else host),
                port=443,
                transport=TransportType.TCP,
            ),
            ProtocolConfig(
                id="vless-default",
                name="VLESS TCP",
                type=ProtocolType.VLESS,
                host=(public_tcp_host if demo else host),
                port=443,
                transport=TransportType.TCP,
            ),
            ProtocolConfig(
                id="reality-default",
                name="Reality (VLESS)",
                type=ProtocolType.REALITY,
                host=(public_tcp_host if demo else host),
                port=443,
                transport=TransportType.TCP,
                meta={"protocol": "vless", "security": "reality"},
            ),
            ProtocolConfig(
                id="trojan-default",
                name="Trojan TCP",
                type=ProtocolType.TROJAN,
                host=(public_tcp_host if demo else host),
                port=443,
                transport=TransportType.TCP,
            ),
            ProtocolConfig(
                id="trojan-go-default",
                name="Trojan-Go TCP",
                type=ProtocolType.TROJAN_GO,
                host=(public_tcp_host if demo else host),
                port=443,
                transport=TransportType.TCP,
            ),
            ProtocolConfig(
                id="hysteria2-default",
                name="Hysteria2 UDP",
                type=ProtocolType.HYSTERIA2,
                host=(public_udp_host if demo else host),
                port=(53 if demo else 443),
                transport=TransportType.UDP,
            ),
            ProtocolConfig(
                id="hysteria-default",
                name="Hysteria UDP",
                type=ProtocolType.HYSTERIA,
                host=(public_udp_host if demo else host),
                port=(53 if demo else 443),
                transport=TransportType.UDP,
            ),
            ProtocolConfig(
                id="tuic-default",
                name="TUIC UDP",
                type=ProtocolType.TUIC,
                host=(public_udp_host if demo else host),
                port=(53 if demo else 443),
                transport=TransportType.UDP,
            ),
            ProtocolConfig(
                id="socks5-default",
                name="SOCKS5 TCP",
                type=ProtocolType.SOCKS5,
                host=(public_tcp_host if demo else host),
                port=(443 if demo else 1080),
                transport=TransportType.TCP,
            ),
            ProtocolConfig(
                id="http-proxy-default",
                name="HTTP Proxy",
                type=ProtocolType.HTTP_PROXY,
                host=(public_tcp_host if demo else host),
                port=(80 if demo else 8080),
                transport=TransportType.TCP,
            ),
            ProtocolConfig(
                id="https-proxy-default",
                name="HTTPS Proxy",
                type=ProtocolType.HTTPS_PROXY,
                host=(public_tcp_host if demo else host),
                port=(443 if demo else 8443),
                transport=TransportType.TCP,
            ),
            ProtocolConfig(
                id="openconnect-default",
                name="OpenConnect TCP",
                type=ProtocolType.OPENCONNECT,
                host=(public_tcp_host if demo else host),
                port=443,
                transport=TransportType.TCP,
            ),
            ProtocolConfig(
                id="ipsec-default",
                name="IPSec UDP",
                type=ProtocolType.IPSEC,
                host=(public_udp_host if demo else host),
                port=(53 if demo else 500),
                transport=TransportType.UDP,
            ),
            ProtocolConfig(
                id="ikev2-default",
                name="IKEv2 UDP",
                type=ProtocolType.IKEV2,
                host=(public_udp_host if demo else host),
                port=(53 if demo else 500),
                transport=TransportType.UDP,
            ),
            ProtocolConfig(
                id="l2tp-default",
                name="L2TP UDP",
                type=ProtocolType.L2TP,
                host=(public_udp_host if demo else host),
                port=(53 if demo else 1701),
                transport=TransportType.UDP,
            ),
            ProtocolConfig(
                id="pptp-default",
                name="PPTP TCP",
                type=ProtocolType.PPTP,
                host=(public_tcp_host if demo else host),
                port=(443 if demo else 1723),
                transport=TransportType.TCP,
            ),
            ProtocolConfig(
                id="sstp-default",
                name="SSTP TCP",
                type=ProtocolType.SSTP,
                host=(public_tcp_host if demo else host),
                port=443,
                transport=TransportType.TCP,
            ),
            ProtocolConfig(
                id="softether-default",
                name="SoftEther TCP",
                type=ProtocolType.SOFTETHER,
                host=(public_tcp_host if demo else host),
                port=(443 if demo else 5555),
                transport=TransportType.TCP,
            ),
            ProtocolConfig(
                id="naive-default",
                name="NaiveProxy TCP",
                type=ProtocolType.NAIVE,
                host=(public_tcp_host if demo else host),
                port=443,
                transport=TransportType.TCP,
            ),
            ProtocolConfig(
                id="brook-default",
                name="Brook TCP",
                type=ProtocolType.BROOK,
                host=(public_tcp_host if demo else host),
                port=(443 if demo else 7000),
                transport=TransportType.TCP,
            ),
            ProtocolConfig(
                id="mtproto-default",
                name="MTProto TCP",
                type=ProtocolType.MTPROTO,
                host=(public_tcp_host if demo else host),
                port=443,
                transport=TransportType.TCP,
            ),
            ProtocolConfig(
                id="generic-http-default",
                name="Generic TCP 80",
                type=ProtocolType.OTHER,
                host=(public_tcp_host if demo else host),
                port=80,
                transport=TransportType.TCP,
            ),
        ]
        for cfg_item in defaults:
            await storage.add_protocol(cfg_item)
        logging.info("Default protocols ensured for host %s", host)

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

        # Start agent API server (for regional reports)
        async def start_api():
            try:
                await run_agent_api(storage, cfg.agent_api_host, cfg.agent_api_port, cfg.agent_token)
            except Exception as exc:  # noqa: BLE001
                logging.exception("Agent API failed: %s", exc)

        try:
            application.create_task(start_api())
        except Exception:  # noqa: BLE001
            asyncio.get_running_loop().create_task(start_api())

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