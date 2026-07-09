"""
Device identity and calibration import/export.

A portable export ties a physical miniEvolver (device_id) to calibration
data. A new server can import this file and trust the device without
reflashing or recalibrating — provided the device's WHO_ARE_YOU identity
and firmware/protocol version are compatible.

Safety: never overwrite existing calibration silently. Import raises
ValueError if the target server_id or device_id doesn't match what is stored.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

try:
    import yaml as _yaml
    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False


@dataclass
class CalibrationData:
    od: dict = field(default_factory=dict)
    temperature: dict = field(default_factory=dict)
    pumps: dict = field(default_factory=dict)


@dataclass
class DeviceExport:
    server_id: str
    device_id: str
    device_type: str = "minievolver"
    firmware_version: str = "unknown"
    protocol_version: int = 2
    calibration: CalibrationData = field(default_factory=CalibrationData)
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if len(self.device_id) > 31:
            raise ValueError(f"device_id too long (max 31): {self.device_id!r}")
        if len(self.server_id) > 31:
            raise ValueError(f"server_id too long (max 31): {self.server_id!r}")

    # ---- Serialisation ----

    def to_dict(self) -> dict:
        d = asdict(self)
        # Ensure metadata has timestamps
        if "created_at" not in d["metadata"]:
            d["metadata"]["created_at"] = _now_iso()
        d["metadata"]["updated_at"] = _now_iso()
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "DeviceExport":
        data = dict(data)
        cal_raw = data.pop("calibration", {})
        cal = CalibrationData(
            od=cal_raw.get("od", {}),
            temperature=cal_raw.get("temperature", {}),
            pumps=cal_raw.get("pumps", {}),
        )
        meta = data.pop("metadata", {})
        return cls(
            server_id=data["server_id"],
            device_id=data["device_id"],
            device_type=data.get("device_type", "minievolver"),
            firmware_version=data.get("firmware_version", "unknown"),
            protocol_version=data.get("protocol_version", 2),
            calibration=cal,
            metadata=meta,
        )

    # ---- Persistence ----

    def save(self, path: str | Path) -> None:
        path = Path(path)
        d = self.to_dict()
        with path.open("w") as f:
            if path.suffix in (".yaml", ".yml"):
                if not _HAS_YAML:
                    raise ImportError("pyyaml required for YAML export: pip install pyyaml")
                _yaml.dump(d, f, default_flow_style=False, allow_unicode=True)
            else:
                json.dump(d, f, indent=2)

    @classmethod
    def load(cls, path: str | Path) -> "DeviceExport":
        path = Path(path)
        with path.open() as f:
            if path.suffix in (".yaml", ".yml"):
                if not _HAS_YAML:
                    raise ImportError("pyyaml required for YAML import: pip install pyyaml")
                data = _yaml.safe_load(f)
            else:
                data = json.load(f)
        return cls.from_dict(data)

    # ---- Compatibility checks ----

    def is_compatible_with_hello(self, hello, min_proto: int = 2) -> bool:
        """Return True if a HelloMessage from the device matches this export."""
        if hello is None:
            return False
        if hello.device_id != self.device_id:
            return False
        if hello.proto_version < min_proto:
            return False
        return True


def new_server_id() -> str:
    """Generate a short stable server identifier."""
    return f"server-{uuid.uuid4().hex[:6]}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
