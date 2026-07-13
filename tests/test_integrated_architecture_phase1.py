import json

import pytest

from evolver.control_plane import ControlPlane
from evolver.control_plane import InvalidTransitionError
from evolver.control_plane import make_runner_action
from evolver.data_service import LocalDataService
from evolver.messages import MessageValidationError
from evolver.messages import make_raw_measurement
from evolver.messages import validate_device_command_request


class RecordingHardwareClient(object):
    def __init__(self):
        self.commands = []

    def send_command(self, command):
        self.commands.append(command)
        return {"accepted": True, "command": command}


def test_raw_measurements_are_written_to_machine_stream(tmp_path):
    data_service = LocalDataService(str(tmp_path))
    envelope = make_raw_measurement(
        "machine-1",
        {"od_90": ["1", "2"], "temp": ["30.0"]},
        producer="evolver-hardwared",
        observed_at="2026-07-13T12:00:00Z",
        metadata={"source": "test"},
    )

    path = data_service.append_raw_measurement(envelope)

    records = data_service.read_records("machines/machine-1/raw")
    assert records == [envelope]
    with open(path) as handle:
        line = handle.readline()
    assert json.loads(line)["kind"] == "machine.measurement.raw"


def test_device_command_validation_accepts_existing_dpu_command_shape():
    command = validate_device_command_request(
        {
            "param": "temp",
            "value": ["NaN"] + [str(3000 + i) for i in range(1, 16)],
            "immediate": True,
            "recurring": False,
            "fields_expected_outgoing": 17,
            "fields_expected_incoming": 17,
            "experiment_id": "exp-1",
        }
    )

    assert command["param"] == "temp"
    assert command["immediate"] is True
    assert command["fields_expected_incoming"] == 17


def test_control_plane_runs_experiment_and_forwards_runner_command(tmp_path):
    hardware = RecordingHardwareClient()
    data_service = LocalDataService(str(tmp_path))
    control_plane = ControlPlane(hardware, data_service=data_service)
    experiment = control_plane.create_experiment(
        {
            "name": "morning run",
            "machine_id": "machine-1",
            "vials": [0, 1],
            "config": {"mode": "turbidostat"},
        },
        experiment_id="exp-1",
    )

    assert experiment["state"] == "created"
    control_plane.start_experiment(
        "exp-1",
        {"kind": "subprocess", "argv": ["dpu"]},
    )
    action = make_runner_action(
        "device_command",
        {
            "experiment_id": "exp-1",
            "param": "stir",
            "value": ["8"] * 16,
            "immediate": True,
        },
        producer="runner-exp-1",
    )

    result = control_plane.handle_runner_action(action)

    assert result["accepted"] is True
    assert hardware.commands == [
        {
            "experiment_id": "exp-1",
            "param": "stir",
            "value": ["8"] * 16,
            "immediate": True,
        }
    ]
    events = data_service.read_records("experiments/exp-1/events")
    assert [event["payload"].get("state") for event in events[:2]] == [
        "created",
        "running",
    ]
    assert events[-1]["kind"] == "experiment.runner.action"


def test_control_plane_rejects_paused_runner_command(tmp_path):
    hardware = RecordingHardwareClient()
    control_plane = ControlPlane(
        hardware,
        data_service=LocalDataService(str(tmp_path)),
    )
    control_plane.create_experiment(
        {"name": "pause test", "machine_id": "machine-1", "vials": [0]},
        experiment_id="exp-1",
    )
    control_plane.start_experiment(
        "exp-1",
        {"kind": "subprocess", "argv": ["dpu"]},
    )
    control_plane.pause_experiment("exp-1", reason="operator request")

    action = make_runner_action(
        "device_command",
        {
            "experiment_id": "exp-1",
            "param": "pump",
            "value": ["0"] * 16,
        },
        producer="runner-exp-1",
    )

    with pytest.raises(InvalidTransitionError):
        control_plane.handle_runner_action(action)
    assert hardware.commands == []


def test_data_service_rejects_unsafe_stream_paths(tmp_path):
    data_service = LocalDataService(str(tmp_path))

    with pytest.raises(MessageValidationError):
        data_service.read_records("../outside")
