"""
Tests for serial port discovery. No real ports opened — monkeypatches
serial.Serial and list_ports so tests run in any environment.
"""

import sys
import os
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from evolver.provisioning import DeviceState
from evolver.serial_discovery import discover_devices, find_known_device, probe_port
from tests.fake_serial import (
    FakeBlankMinievolver,
    FakeProvisionedMinievolver,
    FakeSilentDevice,
    FakeUnknownArduino,
)


def _mock_port_info(device: str):
    info = MagicMock()
    info.device = device
    return info


# ---- probe_port ----

def test_probe_blank_device(monkeypatch):
    dev = FakeBlankMinievolver()
    monkeypatch.setattr("evolver.serial_discovery.serial.Serial", lambda *a, **kw: dev)
    result = probe_port("/dev/ttyACM0")
    assert result.state == DeviceState.UNPROVISIONED

def test_probe_provisioned_device(monkeypatch):
    dev = FakeProvisionedMinievolver("mev-003", "server-a1")
    monkeypatch.setattr("evolver.serial_discovery.serial.Serial", lambda *a, **kw: dev)
    result = probe_port("/dev/ttyACM0")
    assert result.state == DeviceState.KNOWN
    assert result.hello.device_id == "mev-003"

def test_probe_unknown_device(monkeypatch):
    dev = FakeUnknownArduino()
    monkeypatch.setattr("evolver.serial_discovery.serial.Serial", lambda *a, **kw: dev)
    result = probe_port("/dev/ttyUSB0")
    assert result.state == DeviceState.UNKNOWN

def test_probe_silent_device(monkeypatch):
    dev = FakeSilentDevice()
    monkeypatch.setattr("evolver.serial_discovery.serial.Serial", lambda *a, **kw: dev)
    result = probe_port("/dev/ttyACM1")
    assert result.state == DeviceState.UNKNOWN

def test_probe_serial_error(monkeypatch):
    import serial
    def _raise(*a, **kw):
        raise serial.SerialException("permission denied")
    monkeypatch.setattr("evolver.serial_discovery.serial.Serial", _raise)
    result = probe_port("/dev/ttyACM0")
    assert result.state == DeviceState.UNKNOWN
    assert "permission denied" in result.error


# ---- discover_devices ----

def test_discover_finds_minievolver(monkeypatch):
    devs = {
        "/dev/ttyACM0": FakeProvisionedMinievolver("mev-001", "svr"),
        "/dev/ttyUSB0": FakeUnknownArduino(),
    }
    monkeypatch.setattr(
        "evolver.serial_discovery.serial.Serial",
        lambda port, *a, **kw: devs[port],
    )
    results = discover_devices(ports=["/dev/ttyACM0", "/dev/ttyUSB0"])
    assert results["/dev/ttyACM0"].state == DeviceState.KNOWN
    assert results["/dev/ttyUSB0"].state == DeviceState.UNKNOWN

def test_discover_empty_port_list(monkeypatch):
    results = discover_devices(ports=[])
    assert results == {}

def test_discover_with_known_devices_registry(monkeypatch):
    from evolver.identity_store import DeviceExport
    export = DeviceExport(server_id="svr", device_id="mev-001")
    dev = FakeProvisionedMinievolver("mev-001", "svr")
    monkeypatch.setattr(
        "evolver.serial_discovery.serial.Serial",
        lambda *a, **kw: dev,
    )
    results = discover_devices(
        ports=["/dev/ttyACM0"],
        known_devices={"mev-001": export},
    )
    assert results["/dev/ttyACM0"].state == DeviceState.KNOWN

def test_discover_skips_unopenable_port(monkeypatch):
    import serial
    def _fail(port, *a, **kw):
        if port == "/dev/ttyACM0":
            raise serial.SerialException("busy")
        return FakeBlankMinievolver()
    monkeypatch.setattr("evolver.serial_discovery.serial.Serial", _fail)
    results = discover_devices(ports=["/dev/ttyACM0", "/dev/ttyACM1"])
    assert results["/dev/ttyACM0"].state == DeviceState.UNKNOWN
    assert results["/dev/ttyACM1"].state == DeviceState.UNPROVISIONED


# ---- find_known_device ----

def test_find_known_device_found(monkeypatch):
    devs = {
        "/dev/ttyACM0": FakeUnknownArduino(),
        "/dev/ttyACM1": FakeProvisionedMinievolver("mev-003", "svr"),
    }
    monkeypatch.setattr(
        "evolver.serial_discovery.serial.Serial",
        lambda port, *a, **kw: devs[port],
    )
    port = find_known_device("mev-003", ports=["/dev/ttyACM0", "/dev/ttyACM1"])
    assert port == "/dev/ttyACM1"

def test_find_known_device_not_found(monkeypatch):
    monkeypatch.setattr(
        "evolver.serial_discovery.serial.Serial",
        lambda *a, **kw: FakeUnknownArduino(),
    )
    port = find_known_device("mev-999", ports=["/dev/ttyACM0"])
    assert port is None

def test_find_known_device_changes_port(monkeypatch):
    """Device re-plugged at a different port — still found by identity."""
    # Moved from ACM0 to ACM2
    devs = {
        "/dev/ttyACM0": FakeSilentDevice(),
        "/dev/ttyACM2": FakeProvisionedMinievolver("mev-003", "svr"),
    }
    monkeypatch.setattr(
        "evolver.serial_discovery.serial.Serial",
        lambda port, *a, **kw: devs[port],
    )
    port = find_known_device("mev-003", ports=["/dev/ttyACM0", "/dev/ttyACM2"])
    assert port == "/dev/ttyACM2"
