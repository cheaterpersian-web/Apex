from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional, List, Any
from datetime import datetime


class ProtocolType(str, Enum):
    OPENVPN = "openvpn"
    WIREGUARD = "wireguard"
    SHADOWSOCKS = "shadowsocks"
    V2RAY = "v2ray"
    REALITY = "reality"
    OTHER = "other"


class TransportType(str, Enum):
    TCP = "tcp"
    UDP = "udp"


@dataclass
class ClientCommand:
    start_command: str
    socks_port: Optional[int] = None
    ready_regex: Optional[str] = None
    startup_timeout_sec: int = 10


@dataclass
class ProtocolConfig:
    id: str
    name: str
    type: ProtocolType
    host: str
    port: int
    transport: TransportType = TransportType.TCP
    client: Optional[ClientCommand] = None
    meta: Dict[str, Any] = field(default_factory=dict)


class CheckStatus(str, Enum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    ERROR = "error"


@dataclass
class CheckResult:
    protocol_id: str
    status: CheckStatus
    latency_ms: Optional[int] = None
    timestamp_iso: str = field(default_factory=lambda: datetime.utcnow().isoformat(timespec="seconds") + "Z")
    error: Optional[str] = None


@dataclass
class DashboardEntry:
    config: ProtocolConfig
    result: Optional[CheckResult]


@dataclass
class Subscriber:
    user_id: int
    added_iso: str = field(default_factory=lambda: datetime.utcnow().isoformat(timespec="seconds") + "Z")


def protocol_config_from_dict(data: Dict[str, Any]) -> ProtocolConfig:
    client = None
    client_data = data.get("client")
    if client_data:
        client = ClientCommand(
            start_command=client_data["start_command"],
            socks_port=client_data.get("socks_port"),
            ready_regex=client_data.get("ready_regex"),
            startup_timeout_sec=int(client_data.get("startup_timeout_sec", 10)),
        )
    return ProtocolConfig(
        id=str(data["id"]),
        name=str(data.get("name", data["id"])),
        type=ProtocolType(str(data.get("type", "other")).lower()),
        host=str(data["host"]),
        port=int(data["port"]),
        transport=TransportType(str(data.get("transport", "tcp")).lower()),
        client=client,
        meta=dict(data.get("meta", {})),
    )


def protocol_config_to_dict(cfg: ProtocolConfig) -> Dict[str, Any]:
    client: Optional[Dict[str, Any]] = None
    if cfg.client:
        client = {
            "start_command": cfg.client.start_command,
            "socks_port": cfg.client.socks_port,
            "ready_regex": cfg.client.ready_regex,
            "startup_timeout_sec": cfg.client.startup_timeout_sec,
        }
    return {
        "id": cfg.id,
        "name": cfg.name,
        "type": cfg.type.value,
        "host": cfg.host,
        "port": cfg.port,
        "transport": cfg.transport.value,
        "client": client,
        "meta": cfg.meta,
    }