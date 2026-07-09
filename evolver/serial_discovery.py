"""
miniEvolver serial port discovery and device identification.

Scans available serial ports, sends WHO_ARE_YOU, and returns classified results.
Never provisions, recalibrates, or writes to devices — read-only identification only.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

import serial
import serial.tools.list_ports

from .provisioning import (
    DeviceState,
    HelloMessage,
    ProvisioningMode,
    ProvisioningResult,
    ProvisioningStateMachine,
    parse_hello,
)

logger = logging.getLogger(__name__)

WHO_ARE_YOU_CMD = b"WHO_ARE_YOU_!"
DEFAULT_BAUD = 9600
DEFAULT_TIMEOUT = 3.0


def list_serial_ports() -> List[str]:
    """Return all available serial port device paths."""
    return [p.device for p in serial.tools.list_ports.comports()]


def probe_port(port: str, baud: int = DEFAULT_BAUD, timeout: float = DEFAULT_TIMEOUT) -> ProvisioningResult:
    """
    Open a single serial port, send WHO_ARE_YOU, and classify the response.
    Never raises — returns UNKNOWN on any error so callers can iterate safely.
    """
    try:
        with serial.Serial(port, baud, timeout=timeout) as conn:
            conn.write(WHO_ARE_YOU_CMD)
            conn.flush()
            line = conn.readline().decode(errors="replace")
    except serial.SerialException as exc:
        logger.debug("probe_port(%s): serial error: %s", port, exc)
        return ProvisioningResult(state=DeviceState.UNKNOWN, error=str(exc))
    except Exception as exc:
        logger.warning("probe_port(%s): unexpected error: %s", port, exc)
        return ProvisioningResult(state=DeviceState.UNKNOWN, error=str(exc))

    hello = parse_hello(line)
    if hello is None:
        return ProvisioningResult(
            state=DeviceState.UNKNOWN,
            error=f"no valid MEV response (got: {line!r})",
        )

    from .provisioning import classify_device
    state = classify_device(hello)
    return ProvisioningResult(state=state, hello=hello)


def discover_devices(
    ports: Optional[List[str]] = None,
    known_devices: Optional[dict] = None,
    baud: int = DEFAULT_BAUD,
    timeout: float = DEFAULT_TIMEOUT,
) -> Dict[str, ProvisioningResult]:
    """
    Probe all ports (or the given list) and return {port: ProvisioningResult}.
    Skips ports that can't be opened. Never writes to devices.

    known_devices: {device_id: DeviceExport} — enables KNOWN/MISMATCH classification.
    """
    if ports is None:
        ports = list_serial_ports()

    sm = ProvisioningStateMachine(
        mode=ProvisioningMode.ASK,
        known_devices=known_devices or {},
    )

    results: Dict[str, ProvisioningResult] = {}
    for port in ports:
        logger.info("probing %s ...", port)
        try:
            with serial.Serial(port, baud, timeout=timeout) as conn:
                result = sm.identify(conn)
        except serial.SerialException as exc:
            logger.debug("skipping %s: %s", port, exc)
            result = ProvisioningResult(state=DeviceState.UNKNOWN, error=str(exc))
        results[port] = result
        logger.info(
            "  %s → %s%s",
            port,
            result.state.value,
            f" ({result.hello.device_id})" if result.hello and result.hello.device_id else "",
        )
    return results


def find_known_device(
    device_id: str,
    ports: Optional[List[str]] = None,
    baud: int = DEFAULT_BAUD,
    timeout: float = DEFAULT_TIMEOUT,
) -> Optional[str]:
    """
    Scan ports until we find the device with the given device_id.
    Returns the port string, or None if not found.
    """
    for port in (ports or list_serial_ports()):
        result = probe_port(port, baud, timeout)
        if result.hello and result.hello.device_id == device_id:
            return port
    return None
