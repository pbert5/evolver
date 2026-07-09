"""
Fake serial devices for testing without physical hardware.

Each class simulates a different device scenario and implements
the same read/write interface as serial.Serial.
"""

from __future__ import annotations

import io
from typing import Optional


def _crc8(payload: str) -> int:
    crc = 0xFF
    for ch in payload.encode():
        crc ^= ch
        for _ in range(8):
            crc = ((crc << 1) ^ 0x31) if (crc & 0x80) else (crc << 1)
            crc &= 0xFF
    return crc


def _build_hello(device_id=None, owner_id=None, proto=2, fw="0.1") -> bytes:
    dev = device_id or "BLANK"
    owner = owner_id or "BLANK"
    payload = f"type=minievolver,proto={proto},fw={fw},id={dev},owner={owner}"
    crc = _crc8(payload)
    return f"MEV|{proto}|{dev}|1|HELLO|{payload}|{crc:02X}\n".encode()


def _build_provision_ack(device_id, owner_id, proto=2) -> bytes:
    payload = f"id={device_id},owner={owner_id}"
    crc = _crc8(payload)
    return f"MEV|{proto}|{device_id}|2|PROVISION_ACK|{payload}|{crc:02X}\n".encode()


def _build_provision_err(current_id, reason, proto=2) -> bytes:
    payload = f"reason={reason}"
    crc = _crc8(payload)
    return f"MEV|{proto}|{current_id}|2|PROVISION_ERR|{payload}|{crc:02X}\n".encode()


def _build_clear_ack(proto=2) -> bytes:
    payload = "ok=true"
    crc = _crc8(payload)
    return f"MEV|{proto}|BLANK|2|CLEAR_ACK|{payload}|{crc:02X}\n".encode()


class _FakeSerialBase:
    """Base: provides write/flush/readline interface and captures written data."""

    def __init__(self):
        self._written = b""
        self._response: bytes = b""
        self.timeout = 3.0

    def write(self, data: bytes) -> int:
        self._written += data
        return len(data)

    def flush(self):
        pass

    def readline(self) -> bytes:
        """Return the canned response then b'' on subsequent calls."""
        resp = self._response
        self._response = b""
        return resp

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass


class FakeBlankMinievolver(_FakeSerialBase):
    """Valid miniEvolver firmware, no identity stored."""

    def __init__(self, proto=2, fw="0.1"):
        super().__init__()
        self._proto = proto
        self._fw = fw
        self._provisioned = False
        self._device_id: Optional[str] = None
        self._owner_id: Optional[str] = None

    def write(self, data: bytes) -> int:
        super().write(data)
        cmd = data.decode(errors="replace")
        if "WHO_ARE_YOU" in cmd:
            self._response = _build_hello(
                device_id=self._device_id,
                owner_id=self._owner_id,
                proto=self._proto,
                fw=self._fw,
            )
        elif cmd.startswith("PROVISION,"):
            if self._provisioned:
                self._response = _build_provision_err(self._device_id, "already_provisioned")
            else:
                # Parse PROVISION,<dev>,<owner>_!
                body = cmd.replace("_!", "").strip()
                parts = body.split(",")
                if len(parts) == 3:
                    _, dev_id, owner_id = parts
                    self._device_id = dev_id.strip()
                    self._owner_id = owner_id.strip()
                    self._provisioned = True
                    self._response = _build_provision_ack(self._device_id, self._owner_id)
                else:
                    self._response = _build_provision_err("BLANK", "bad_format")
        elif "CLEAR_ID" in cmd:
            self._device_id = None
            self._owner_id = None
            self._provisioned = False
            self._response = _build_clear_ack()
        return len(data)


class FakeProvisionedMinievolver(_FakeSerialBase):
    """miniEvolver with an already-assigned identity."""

    def __init__(self, device_id: str, owner_id: str, proto=2, fw="0.1"):
        super().__init__()
        self._device_id = device_id
        self._owner_id = owner_id
        self._proto = proto
        self._fw = fw

    def write(self, data: bytes) -> int:
        super().write(data)
        cmd = data.decode(errors="replace")
        if "WHO_ARE_YOU" in cmd:
            self._response = _build_hello(
                device_id=self._device_id,
                owner_id=self._owner_id,
                proto=self._proto,
                fw=self._fw,
            )
        elif cmd.startswith("PROVISION,"):
            self._response = _build_provision_err(self._device_id, "already_provisioned")
        elif "CLEAR_ID" in cmd:
            # Simulates a device that was cleared
            self._response = _build_clear_ack()
        return len(data)


class FakeUnknownArduino(_FakeSerialBase):
    """Arbitrary Arduino that doesn't speak the miniEvolver protocol."""

    def write(self, data: bytes) -> int:
        super().write(data)
        # Sends garbage or nothing in response to WHO_ARE_YOU
        self._response = b"??\r\n"
        return len(data)


class FakeSilentDevice(_FakeSerialBase):
    """Serial device that never responds (timeout scenario)."""

    def write(self, data: bytes) -> int:
        super().write(data)
        self._response = b""  # simulate timeout
        return len(data)

    def readline(self) -> bytes:
        return b""


class FakeOldFirmware(_FakeSerialBase):
    """Old miniEvolver firmware that doesn't support WHO_ARE_YOU."""

    def write(self, data: bytes) -> int:
        super().write(data)
        # Responds to evolver_si commands but ignores WHO_ARE_YOU
        self._response = b""
        return len(data)


class FakeCorruptedResponse(_FakeSerialBase):
    """Returns a WHO_ARE_YOU response with a bad CRC."""

    def write(self, data: bytes) -> int:
        super().write(data)
        if b"WHO_ARE_YOU" in data:
            # Build a valid frame then corrupt the CRC byte
            good = _build_hello().decode()
            parts = good.strip().split("|")
            parts[-1] = "00\n"
            self._response = "|".join(parts).encode()
        return len(data)


class FakeWrongProtoVersion(_FakeSerialBase):
    """Returns a HELLO with an unsupported protocol version."""

    def write(self, data: bytes) -> int:
        super().write(data)
        if b"WHO_ARE_YOU" in data:
            self._response = _build_hello(proto=1)
        return len(data)
