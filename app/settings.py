from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

import yaml
from dotenv import load_dotenv


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _env_str(name: str, default: str) -> str:
    value = os.getenv(name)
    return value if value is not None else default


@dataclass
class AppConfig:
    telegram_bot_token: str
    check_interval_seconds: int
    proxy_test_url: str
    storage_dir: str
    tcp_timeout_seconds: int
    udp_timeout_seconds: int
    agent_token: Optional[str] = None
    agent_api_host: str = "0.0.0.0"
    agent_api_port: int = 8088


def load_config(config_path: Optional[str] = None) -> AppConfig:
    load_dotenv()

    # Base defaults
    defaults = {
        "check_interval_seconds": 60,
        "proxy_test_url": "https://www.google.com/generate_204",
        "storage_dir": "./data",
        "tcp_timeout_seconds": 5,
        "udp_timeout_seconds": 3,
        "agent_api_host": "0.0.0.0",
        "agent_api_port": 8088,
    }

    file_cfg = {}
    if config_path is None:
        # try default
        default_path = os.path.abspath(os.path.join(os.getcwd(), "config.yaml"))
        if os.path.exists(default_path):
            config_path = default_path
    if config_path and os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            file_cfg = yaml.safe_load(f) or {}

    telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    agent_token_env = os.getenv("AGENT_TOKEN")

    return AppConfig(
        telegram_bot_token=telegram_bot_token,
        check_interval_seconds=int(file_cfg.get("check_interval_seconds", _env_int("CHECK_INTERVAL_SECONDS", defaults["check_interval_seconds"]))),
        proxy_test_url=str(file_cfg.get("proxy_test_url", _env_str("TEST_URL", defaults["proxy_test_url"]))),
        storage_dir=str(file_cfg.get("storage_dir", defaults["storage_dir"])),
        tcp_timeout_seconds=int(file_cfg.get("tcp_timeout_seconds", defaults["tcp_timeout_seconds"])),
        udp_timeout_seconds=int(file_cfg.get("udp_timeout_seconds", defaults["udp_timeout_seconds"])),
        agent_token=str(file_cfg.get("agent_token", agent_token_env)) if (file_cfg.get("agent_token", agent_token_env) is not None) else None,
        agent_api_host=str(file_cfg.get("agent_api_host", _env_str("AGENT_API_HOST", defaults["agent_api_host"]))),
        agent_api_port=int(file_cfg.get("agent_api_port", _env_int("AGENT_API_PORT", defaults["agent_api_port"]))),
    )