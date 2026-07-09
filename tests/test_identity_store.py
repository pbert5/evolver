"""Tests for DeviceExport serialisation and compatibility checks."""

import json
import tempfile
from pathlib import Path

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from evolver.identity_store import CalibrationData, DeviceExport, new_server_id
from evolver.provisioning import HelloMessage


# ---- Construction ----

def test_device_export_basic():
    e = DeviceExport(server_id="svr", device_id="mev-001")
    assert e.device_type == "minievolver"
    assert e.protocol_version == 2

def test_device_id_too_long_raises():
    with pytest.raises(ValueError, match="device_id too long"):
        DeviceExport(server_id="svr", device_id="x" * 32)

def test_server_id_too_long_raises():
    with pytest.raises(ValueError, match="server_id too long"):
        DeviceExport(server_id="s" * 32, device_id="mev-001")


# ---- Serialisation round-trip (JSON) ----

def test_json_roundtrip(tmp_path):
    cal = CalibrationData(od={"slope": 1.5}, temperature={"offset": -0.2})
    e = DeviceExport(
        server_id="svr-001",
        device_id="mev-003",
        calibration=cal,
        metadata={"notes": "test unit"},
    )
    path = tmp_path / "device.json"
    e.save(path)
    loaded = DeviceExport.load(path)
    assert loaded.device_id == "mev-003"
    assert loaded.server_id == "svr-001"
    assert loaded.calibration.od == {"slope": 1.5}
    assert loaded.calibration.temperature == {"offset": -0.2}
    assert loaded.metadata["notes"] == "test unit"

def test_json_adds_updated_at(tmp_path):
    e = DeviceExport(server_id="svr", device_id="mev-001")
    path = tmp_path / "device.json"
    e.save(path)
    data = json.loads(path.read_text())
    assert "updated_at" in data["metadata"]
    assert "created_at" in data["metadata"]

def test_from_dict_minimal():
    data = {"server_id": "svr", "device_id": "mev-001"}
    e = DeviceExport.from_dict(data)
    assert e.device_id == "mev-001"
    assert e.calibration.od == {}


# ---- YAML round-trip ----

def test_yaml_roundtrip(tmp_path):
    pytest.importorskip("yaml")
    e = DeviceExport(server_id="svr", device_id="mev-005",
                     calibration=CalibrationData(pumps={"pump0": 1.0}))
    path = tmp_path / "device.yaml"
    e.save(path)
    loaded = DeviceExport.load(path)
    assert loaded.device_id == "mev-005"
    assert loaded.calibration.pumps == {"pump0": 1.0}

def test_yaml_extension_required_for_yaml_output(tmp_path):
    e = DeviceExport(server_id="svr", device_id="mev-001")
    path = tmp_path / "device.json"
    e.save(path)
    # JSON output even with pyyaml installed when extension is .json
    data = json.loads(path.read_text())
    assert "device_id" in data


# ---- Compatibility checks ----

def _hello(device_id="mev-003", proto=2, crc_ok=True):
    return HelloMessage(
        device_type="minievolver", proto_version=proto, fw_version="0.1",
        device_id=device_id, owner_id="svr", seq=1, crc_ok=crc_ok,
    )

def test_compatible_with_matching_hello():
    e = DeviceExport(server_id="svr", device_id="mev-003")
    assert e.is_compatible_with_hello(_hello("mev-003")) is True

def test_incompatible_wrong_device_id():
    e = DeviceExport(server_id="svr", device_id="mev-003")
    assert e.is_compatible_with_hello(_hello("mev-999")) is False

def test_incompatible_old_proto():
    e = DeviceExport(server_id="svr", device_id="mev-003")
    assert e.is_compatible_with_hello(_hello(proto=1), min_proto=2) is False

def test_incompatible_none_hello():
    e = DeviceExport(server_id="svr", device_id="mev-003")
    assert e.is_compatible_with_hello(None) is False


# ---- new_server_id ----

def test_new_server_id_format():
    sid = new_server_id()
    assert sid.startswith("server-")
    assert len(sid) == len("server-") + 6

def test_new_server_id_unique():
    ids = {new_server_id() for _ in range(20)}
    assert len(ids) == 20  # no collisions
