from __future__ import annotations

import asyncio
import json
import os
from typing import Dict, List, Optional

from .models import ProtocolConfig, protocol_config_from_dict, protocol_config_to_dict, CheckResult, Subscriber


class JsonStorage:
    def __init__(self, storage_dir: str) -> None:
        self.storage_dir = os.path.abspath(storage_dir)
        self._lock = asyncio.Lock()
        os.makedirs(self.storage_dir, exist_ok=True)
        self._paths = {
            "protocols": os.path.join(self.storage_dir, "protocols.json"),
            "status": os.path.join(self.storage_dir, "status.json"),
            "subscribers": os.path.join(self.storage_dir, "subscribers.json"),
            "status_regions": os.path.join(self.storage_dir, "status_regions.json"),
        }
        # Ensure files exist
        for key, path in self._paths.items():
            if not os.path.exists(path):
                with open(path, "w", encoding="utf-8") as f:
                    if key == "protocols":
                        json.dump([], f)
                    elif key == "status":
                        json.dump({}, f)
                    elif key == "subscribers":
                        json.dump([], f)
                    elif key == "status_regions":
                        json.dump({}, f)

    async def _read_json(self, key: str):
        async with self._lock:
            path = self._paths[key]
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except json.JSONDecodeError:
                return [] if key in {"protocols", "subscribers"} else {}

    async def _write_json(self, key: str, data) -> None:
        async with self._lock:
            path = self._paths[key]
            tmp_path = path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, path)

    # Protocols
    async def list_protocols(self) -> List[ProtocolConfig]:
        raw = await self._read_json("protocols")
        return [protocol_config_from_dict(item) for item in raw]

    async def add_protocol(self, cfg: ProtocolConfig) -> None:
        items = await self._read_json("protocols")
        if any(item.get("id") == cfg.id for item in items):
            # replace
            items = [protocol_config_to_dict(cfg) if item.get("id") == cfg.id else item for item in items]
        else:
            items.append(protocol_config_to_dict(cfg))
        await self._write_json("protocols", items)

    async def remove_protocol(self, protocol_id: str) -> bool:
        items = await self._read_json("protocols")
        new_items = [item for item in items if item.get("id") != protocol_id]
        changed = len(new_items) != len(items)
        if changed:
            await self._write_json("protocols", new_items)
        # also drop status
        status = await self._read_json("status")
        if protocol_id in status:
            del status[protocol_id]
            await self._write_json("status", status)
        return changed

    # Statuses
    async def get_status(self) -> Dict[str, CheckResult]:
        raw = await self._read_json("status")
        # Keep as raw dicts to avoid serialization overhead; callers can interpret
        return raw

    async def update_status(self, result: CheckResult) -> None:
        status = await self._read_json("status")
        status[result.protocol_id] = {
            "protocol_id": result.protocol_id,
            "status": result.status.value,
            "latency_ms": result.latency_ms,
            "timestamp_iso": result.timestamp_iso,
            "error": result.error,
        }
        await self._write_json("status", status)

    # Regional Statuses
    async def get_region_status(self, region: str) -> Dict[str, CheckResult]:
        all_regions = await self._read_json("status_regions")
        return all_regions.get(region, {})

    async def update_region_status(self, region: str, result: CheckResult) -> None:
        all_regions = await self._read_json("status_regions")
        region_map = all_regions.get(region, {})
        region_map[result.protocol_id] = {
            "protocol_id": result.protocol_id,
            "status": result.status.value,
            "latency_ms": result.latency_ms,
            "timestamp_iso": result.timestamp_iso,
            "error": result.error,
        }
        all_regions[region] = region_map
        await self._write_json("status_regions", all_regions)

    # Subscribers
    async def list_subscribers(self) -> List[Subscriber]:
        raw = await self._read_json("subscribers")
        return [Subscriber(user_id=int(item["user_id"]), added_iso=str(item.get("added_iso", ""))) for item in raw]

    async def add_subscriber(self, user_id: int) -> None:
        items = await self._read_json("subscribers")
        if not any(int(item.get("user_id")) == user_id for item in items):
            from .utils import utc_iso_now
            items.append({"user_id": user_id, "added_iso": utc_iso_now()})
            await self._write_json("subscribers", items)

    async def remove_subscriber(self, user_id: int) -> bool:
        items = await self._read_json("subscribers")
        new_items = [item for item in items if int(item.get("user_id")) != user_id]
        changed = len(new_items) != len(items)
        if changed:
            await self._write_json("subscribers", new_items)
        return changed