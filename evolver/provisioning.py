"""
miniEvolver device identity and provisioning state machine.

Server-side counterpart to identity.h. Handles WHO_ARE_YOU handshake,
classifies device state, and guards against unsafe reprovisioning.

Safety rules:
- Never silently reprovision a KNOWN device.
- Never bind calibration to an UNKNOWN or MISMATCH device.
- ProvisioningMode.AUTO is only for CI / simulation environments.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class DeviceState(Enum):
    UNKNOWN = "UNKNOWN"             # no response or unrecognised protocol
    UNPROVISIONED = "UNPROVISIONED" # valid miniEvolver firmware, no identity stored
    KNOWN = "KNOWN"                 # identity matches this server's config
    MISMATCH = "MISMATCH"           # identity exists but doesn't match expected


class ProvisioningMode(Enum):
    ASK = "ask"       # default: ask user before any identity write
    BUTTON = "button" # require physical hardware confirmation
    AUTO = "auto"     # for CI / simulation only — never for real experiments


@dataclass
class HelloMessage:
    device_type: str
    proto_version: int
    fw_version: str
    device_id: Optional[str]    # None means BLANK (unprovisioned)
    owner_id: Optional[str]
    seq: int
    crc_ok: bool
    raw: str = ""


@dataclass
class ProvisioningResult:
    state: DeviceState
    hello: Optional[HelloMessage] = None
    error: Optional[str] = None


_HELLO_RE = re.compile(
    r"^MEV\|(?P<proto>\d+)\|(?P<dev_id>[^|]+)\|(?P<seq>\d+)\|HELLO\|(?P<payload>[^|]+)\|(?P<crc>[0-9A-Fa-f]{2})$"
)

_PROV_ACK_RE = re.compile(
    r"^MEV\|\d+\|(?P<dev_id>[^|]+)\|\d+\|PROVISION_ACK\|(?P<payload>[^|]+)\|[0-9A-Fa-f]{2}$"
)

_PROV_ERR_RE = re.compile(
    r"^MEV\|\d+\|[^|]+\|\d+\|PROVISION_ERR\|reason=(?P<reason>[^|]+)\|[0-9A-Fa-f]{2}$"
)


def _crc8(payload: str) -> int:
    """CRC8 Dallas/Maxim 1-Wire (poly=0x31, init=0xFF) — mirrors identity.h."""
    crc = 0xFF
    for ch in payload.encode():
        crc ^= ch
        for _ in range(8):
            crc = ((crc << 1) ^ 0x31) if (crc & 0x80) else (crc << 1)
            crc &= 0xFF
    return crc


def parse_hello(line: str) -> Optional[HelloMessage]:
    """
    Parse a WHO_ARE_YOU response from the device.
    Returns None for any parse error (caller treats as UNKNOWN device).
    """
    m = _HELLO_RE.match(line.strip())
    if not m:
        return None
    payload = m.group("payload")
    expected_crc = _crc8(payload)
    received_crc = int(m.group("crc"), 16)
    fields = dict(
        kv.split("=", 1) for kv in payload.split(",") if "=" in kv
    )
    raw_id = m.group("dev_id")
    return HelloMessage(
        device_type=fields.get("type", ""),
        proto_version=int(m.group("proto")),
        fw_version=fields.get("fw", ""),
        device_id=None if raw_id == "BLANK" else raw_id,
        owner_id=None if fields.get("owner") == "BLANK" else fields.get("owner"),
        seq=int(m.group("seq")),
        crc_ok=(expected_crc == received_crc),
        raw=line.strip(),
    )


def classify_device(
    hello: Optional[HelloMessage],
    expected_device_id: Optional[str] = None,
    expected_owner_id: Optional[str] = None,
    min_proto_version: int = 2,
) -> DeviceState:
    """
    Classify a device based on its HELLO message and what this server expects.

    expected_device_id: if set, KNOWN requires this exact device_id.
    expected_owner_id: if set, KNOWN requires this exact owner_id.
    """
    if hello is None:
        return DeviceState.UNKNOWN
    if not hello.crc_ok:
        return DeviceState.UNKNOWN
    if hello.device_type != "minievolver":
        return DeviceState.UNKNOWN
    if hello.proto_version < min_proto_version:
        return DeviceState.UNKNOWN
    if hello.device_id is None:
        return DeviceState.UNPROVISIONED

    # Device has an identity — check if it matches expectations
    if expected_device_id is not None and hello.device_id != expected_device_id:
        return DeviceState.MISMATCH
    if expected_owner_id is not None and hello.owner_id != expected_owner_id:
        return DeviceState.MISMATCH
    return DeviceState.KNOWN


class ProvisioningStateMachine:
    """
    Manages provisioning state for a single serial port connection.

    Usage:
        sm = ProvisioningStateMachine(mode=ProvisioningMode.ASK,
                                      known_devices={"mev-003": export})
        result = sm.identify(serial_port)
        if result.state == DeviceState.KNOWN:
            # safe to use
    """

    WHO_ARE_YOU_CMD = b"WHO_ARE_YOU_!"
    PROVISION_CMD_FMT = "PROVISION,{device_id},{owner_id}_!"
    CLEAR_ID_CMD = b"CLEAR_ID_!"

    def __init__(
        self,
        mode: ProvisioningMode = ProvisioningMode.ASK,
        known_devices: Optional[dict] = None,
        min_proto_version: int = 2,
    ):
        self.mode = mode
        # device_id -> DeviceExport (imported from identity_store)
        self.known_devices: dict = known_devices or {}
        self.min_proto_version = min_proto_version

    def identify(self, conn, timeout: float = 5.0) -> ProvisioningResult:
        """
        Send WHO_ARE_YOU and classify the response.
        conn must be a serial.Serial-like object (read/write/readline).
        """
        conn.write(self.WHO_ARE_YOU_CMD)
        conn.flush()
        try:
            conn.timeout = timeout
            line = conn.readline().decode(errors="replace")
        except Exception as exc:
            return ProvisioningResult(state=DeviceState.UNKNOWN, error=str(exc))

        hello = parse_hello(line)
        if hello is None:
            return ProvisioningResult(
                state=DeviceState.UNKNOWN,
                error=f"unparseable response: {line!r}",
            )

        # Look up expected identity from our known-devices registry
        expected_id = None
        expected_owner = None
        if hello.device_id and hello.device_id in self.known_devices:
            export = self.known_devices[hello.device_id]
            expected_id = export.device_id
            expected_owner = export.server_id

        state = classify_device(
            hello,
            expected_device_id=expected_id,
            expected_owner_id=expected_owner,
            min_proto_version=self.min_proto_version,
        )
        return ProvisioningResult(state=state, hello=hello)

    def provision(self, conn, device_id: str, owner_id: str, timeout: float = 5.0) -> bool:
        """
        Write identity to an UNPROVISIONED device.
        Returns True on success. Raises RuntimeError if mode is not AUTO
        and caller hasn't handled confirmation.
        """
        if self.mode == ProvisioningMode.BUTTON:
            raise RuntimeError(
                "button mode: confirm physical action on device before calling provision()"
            )

        cmd = self.PROVISION_CMD_FMT.format(device_id=device_id, owner_id=owner_id)
        conn.write(cmd.encode())
        conn.flush()
        conn.timeout = timeout
        line = conn.readline().decode(errors="replace").strip()

        m = _PROV_ACK_RE.match(line)
        if m:
            return True
        m_err = _PROV_ERR_RE.match(line)
        if m_err:
            raise RuntimeError(f"device refused provisioning: {m_err.group('reason')}")
        raise RuntimeError(f"unexpected provisioning response: {line!r}")

    def clear_identity(self, conn, timeout: float = 5.0) -> bool:
        """
        Clear stored identity from device (prerequisite for reprovisioning).
        Only succeeds in AUTO mode; ASK and BUTTON require explicit user action.
        """
        if self.mode != ProvisioningMode.AUTO:
            raise RuntimeError(
                "clear_identity() in non-AUTO mode requires explicit user confirmation; "
                "send CLEAR_ID_! manually after confirming with the operator"
            )
        conn.write(self.CLEAR_ID_CMD)
        conn.flush()
        conn.timeout = timeout
        line = conn.readline().decode(errors="replace").strip()
        return "CLEAR_ACK" in line
