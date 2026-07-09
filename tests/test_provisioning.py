"""
Tests for the server-side provisioning state machine.
No hardware required — uses FakeSerial devices.
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from evolver.provisioning import (
    DeviceState,
    ProvisioningMode,
    ProvisioningResult,
    ProvisioningStateMachine,
    classify_device,
    parse_hello,
)
from tests.fake_serial import (
    FakeBlankMinievolver,
    FakeCorruptedResponse,
    FakeOldFirmware,
    FakeProvisionedMinievolver,
    FakeSilentDevice,
    FakeUnknownArduino,
    FakeWrongProtoVersion,
)


# ---- identify() ----

def test_identify_blank_device():
    dev = FakeBlankMinievolver()
    sm = ProvisioningStateMachine()
    result = sm.identify(dev)
    assert result.state == DeviceState.UNPROVISIONED
    assert result.hello is not None
    assert result.hello.device_id is None

def test_identify_known_device_no_registry():
    dev = FakeProvisionedMinievolver("mev-003", "server-a1")
    sm = ProvisioningStateMachine()
    result = sm.identify(dev)
    # No known_devices registry → any provisioned device is KNOWN
    assert result.state == DeviceState.KNOWN

def test_identify_known_device_matching_registry():
    from evolver.identity_store import DeviceExport
    export = DeviceExport(server_id="server-a1", device_id="mev-003")
    dev = FakeProvisionedMinievolver("mev-003", "server-a1")
    sm = ProvisioningStateMachine(known_devices={"mev-003": export})
    result = sm.identify(dev)
    assert result.state == DeviceState.KNOWN

def test_identify_mismatch_device_id():
    from evolver.identity_store import DeviceExport
    export = DeviceExport(server_id="server-a1", device_id="mev-999")  # different ID expected
    dev = FakeProvisionedMinievolver("mev-003", "server-a1")
    sm = ProvisioningStateMachine(known_devices={"mev-999": export})
    result = sm.identify(dev)
    # mev-003 is not in registry → treat as KNOWN (unregistered provisioned device)
    # (mismatch only fires when the device_id IS in our registry but something else differs)
    assert result.state == DeviceState.KNOWN

def test_identify_unknown_arduino():
    dev = FakeUnknownArduino()
    sm = ProvisioningStateMachine()
    result = sm.identify(dev)
    assert result.state == DeviceState.UNKNOWN

def test_identify_silent_device():
    dev = FakeSilentDevice()
    sm = ProvisioningStateMachine()
    result = sm.identify(dev)
    assert result.state == DeviceState.UNKNOWN

def test_identify_old_firmware():
    dev = FakeOldFirmware()
    sm = ProvisioningStateMachine()
    result = sm.identify(dev)
    assert result.state == DeviceState.UNKNOWN

def test_identify_corrupted_crc():
    dev = FakeCorruptedResponse()
    sm = ProvisioningStateMachine()
    result = sm.identify(dev)
    assert result.state == DeviceState.UNKNOWN

def test_identify_wrong_proto_version():
    dev = FakeWrongProtoVersion()
    sm = ProvisioningStateMachine(min_proto_version=2)
    result = sm.identify(dev)
    assert result.state == DeviceState.UNKNOWN


# ---- provision() ----

def test_provision_blank_device_auto_mode():
    dev = FakeBlankMinievolver()
    sm = ProvisioningStateMachine(mode=ProvisioningMode.AUTO)
    assert sm.provision(dev, "mev-new", "server-x") is True

def test_provision_already_provisioned_raises():
    dev = FakeProvisionedMinievolver("mev-003", "server-a1")
    sm = ProvisioningStateMachine(mode=ProvisioningMode.AUTO)
    with pytest.raises(RuntimeError, match="already_provisioned"):
        sm.provision(dev, "mev-new", "server-x")

def test_provision_button_mode_raises_before_send():
    dev = FakeBlankMinievolver()
    sm = ProvisioningStateMachine(mode=ProvisioningMode.BUTTON)
    with pytest.raises(RuntimeError, match="button mode"):
        sm.provision(dev, "mev-new", "server-x")

def test_provision_blank_then_identify_shows_known():
    dev = FakeBlankMinievolver()
    sm = ProvisioningStateMachine(mode=ProvisioningMode.AUTO)
    # First: blank
    r1 = sm.identify(dev)
    assert r1.state == DeviceState.UNPROVISIONED
    # Provision
    sm.provision(dev, "mev-001", "server-y")
    # Now: known
    r2 = sm.identify(dev)
    assert r2.state == DeviceState.KNOWN
    assert r2.hello.device_id == "mev-001"


# ---- clear_identity() ----

def test_clear_identity_auto_mode():
    dev = FakeProvisionedMinievolver("mev-003", "server-a1")
    sm = ProvisioningStateMachine(mode=ProvisioningMode.AUTO)
    assert sm.clear_identity(dev) is True

def test_clear_identity_ask_mode_raises():
    dev = FakeProvisionedMinievolver("mev-003", "server-a1")
    sm = ProvisioningStateMachine(mode=ProvisioningMode.ASK)
    with pytest.raises(RuntimeError, match="non-AUTO mode"):
        sm.clear_identity(dev)

def test_provision_after_clear():
    dev = FakeBlankMinievolver()
    sm = ProvisioningStateMachine(mode=ProvisioningMode.AUTO)
    sm.provision(dev, "mev-003", "server-a1")
    # Reprovisioning without clear should fail
    with pytest.raises(RuntimeError, match="already_provisioned"):
        sm.provision(dev, "mev-999", "server-z")
    # Clear then reprovision
    sm.clear_identity(dev)
    assert sm.provision(dev, "mev-999", "server-z") is True


# ---- classify_device() ----

def test_classify_none_hello():
    assert classify_device(None) == DeviceState.UNKNOWN

def test_classify_bad_crc():
    from evolver.provisioning import HelloMessage
    hello = HelloMessage(
        device_type="minievolver", proto_version=2, fw_version="0.1",
        device_id=None, owner_id=None, seq=1, crc_ok=False,
    )
    assert classify_device(hello) == DeviceState.UNKNOWN

def test_classify_wrong_device_type():
    from evolver.provisioning import HelloMessage
    hello = HelloMessage(
        device_type="unknown_device", proto_version=2, fw_version="0.1",
        device_id=None, owner_id=None, seq=1, crc_ok=True,
    )
    assert classify_device(hello) == DeviceState.UNKNOWN

def test_classify_old_proto():
    from evolver.provisioning import HelloMessage
    hello = HelloMessage(
        device_type="minievolver", proto_version=1, fw_version="0.0.9",
        device_id=None, owner_id=None, seq=1, crc_ok=True,
    )
    assert classify_device(hello, min_proto_version=2) == DeviceState.UNKNOWN

def test_classify_unprovisioned():
    from evolver.provisioning import HelloMessage
    hello = HelloMessage(
        device_type="minievolver", proto_version=2, fw_version="0.1",
        device_id=None, owner_id=None, seq=1, crc_ok=True,
    )
    assert classify_device(hello) == DeviceState.UNPROVISIONED

def test_classify_known_no_expectations():
    from evolver.provisioning import HelloMessage
    hello = HelloMessage(
        device_type="minievolver", proto_version=2, fw_version="0.1",
        device_id="mev-003", owner_id="server-a1", seq=1, crc_ok=True,
    )
    assert classify_device(hello) == DeviceState.KNOWN

def test_classify_mismatch_device_id():
    from evolver.provisioning import HelloMessage
    hello = HelloMessage(
        device_type="minievolver", proto_version=2, fw_version="0.1",
        device_id="mev-003", owner_id="server-a1", seq=1, crc_ok=True,
    )
    assert classify_device(hello, expected_device_id="mev-999") == DeviceState.MISMATCH

def test_classify_mismatch_owner_id():
    from evolver.provisioning import HelloMessage
    hello = HelloMessage(
        device_type="minievolver", proto_version=2, fw_version="0.1",
        device_id="mev-003", owner_id="server-a1", seq=1, crc_ok=True,
    )
    assert classify_device(hello, expected_owner_id="server-z") == DeviceState.MISMATCH
