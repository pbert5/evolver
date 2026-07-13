import pytest

from evolver.broadcast_ingest import BroadcastIngestor
from evolver.broadcast_ingest import broadcast_to_raw_measurement
from evolver.control_api import create_control_plane_app
from evolver.control_plane import ControlPlane
from evolver.data_service import LocalDataService
from evolver.maintenance_jobs import JOB_PENDING_AUTHORIZATION
from evolver.maintenance_jobs import JOB_QUEUED
from evolver.maintenance_jobs import JOB_SUCCEEDED
from evolver.maintenance_jobs import MaintenanceJobManager
from evolver.messages import MessageValidationError
from evolver.runner_manager import DpuRunnerManager
from evolver.runner_manager import RUNNER_EXITED
from evolver.runner_manager import RUNNER_RUNNING


class RecordingHardwareClient(object):
    def __init__(self):
        self.commands = []

    def send_command(self, command):
        self.commands.append(command)
        return {"accepted": True, "command": command}


class FakeProcess(object):
    def __init__(self):
        self.returncode = None
        self.signals = []
        self.terminated = False
        self.killed = False

    def poll(self):
        return self.returncode

    def send_signal(self, signal_number):
        self.signals.append(signal_number)

    def terminate(self):
        self.terminated = True
        self.returncode = 0

    def kill(self):
        self.killed = True
        self.returncode = -9

    def wait(self, timeout=None):
        if self.returncode is None:
            self.returncode = 0
        return self.returncode


def test_broadcast_ingestor_persists_existing_server_broadcast(tmp_path):
    data_service = LocalDataService(str(tmp_path))
    ingestor = BroadcastIngestor(data_service)
    broadcast = {
        "data": {"od_90": ["b", "1", "2"], "temp": ["b", "30.1"]},
        "config": {"temp": {"fields_expected_incoming": 17}},
        "ip": "127.0.0.1",
        "timestamp": 0,
    }

    envelope = ingestor.ingest(broadcast)

    assert envelope["payload"]["machine_id"] == "evolver-127-0-0-1"
    assert envelope["payload"]["observed_at"] == "1970-01-01T00:00:00Z"
    records = data_service.read_records("machines/evolver-127-0-0-1/raw")
    assert records == [envelope]


def test_broadcast_adapter_requires_measurements():
    with pytest.raises(MessageValidationError):
        broadcast_to_raw_measurement(
            {"data": {}, "ip": "127.0.0.1"},
            producer="test",
        )


def test_dpu_runner_manager_launches_current_dpu_script_shape(tmp_path):
    dpu_dir = tmp_path / "dpu"
    script_dir = dpu_dir / "experiment" / "template"
    script_dir.mkdir(parents=True)
    script_path = script_dir / "eVOLVER.py"
    script_path.write_text("print('runner')\n")
    created = []

    def popen_factory(argv, **kwargs):
        process = FakeProcess()
        created.append((argv, kwargs, process))
        return process

    manager = DpuRunnerManager(
        python_executable="/usr/bin/python",
        popen_factory=popen_factory,
    )

    runner = manager.start_dpu_runner(
        "exp-1",
        str(dpu_dir),
        ip_address="127.0.0.1",
        experiment_dir="/tmp/exp-1",
        extra_args=["--exit-after-broadcasts", "1"],
    )

    assert runner["state"] == RUNNER_RUNNING
    assert created[0][0] == [
        "/usr/bin/python",
        str(script_path),
        "--ip-address",
        "127.0.0.1",
        "--experiment-dir",
        "/tmp/exp-1",
        "--exit-after-broadcasts",
        "1",
    ]
    assert created[0][1]["cwd"] == str(dpu_dir)
    created[0][2].returncode = 0
    assert manager.runner_status("exp-1")["state"] == RUNNER_EXITED


def test_maintenance_job_requires_authorization_and_records_events(tmp_path):
    data_service = LocalDataService(str(tmp_path))
    manager = MaintenanceJobManager(data_service=data_service)

    job = manager.create_job(
        "firmware_flash",
        {"machine_id": "machine-1", "artifact": "approved.hex"},
        job_id="job-1",
    )
    assert job["state"] == JOB_PENDING_AUTHORIZATION

    authorized = manager.authorize_job("job-1", approved=True)
    assert authorized["state"] == JOB_QUEUED

    finished = manager.run_job(
        "job-1",
        lambda payload: {"flashed": payload["artifact"]},
    )

    assert finished["state"] == JOB_SUCCEEDED
    assert finished["result"] == {"flashed": "approved.hex"}
    events = data_service.read_records("jobs/job-1/events")
    assert [event["payload"]["state"] for event in events] == [
        JOB_PENDING_AUTHORIZATION,
        JOB_QUEUED,
        "running",
        JOB_SUCCEEDED,
    ]


def test_control_plane_api_exposes_local_service_routes(tmp_path):
    control_plane = ControlPlane(
        RecordingHardwareClient(),
        data_service=LocalDataService(str(tmp_path)),
    )
    app = create_control_plane_app(
        control_plane,
        job_manager=MaintenanceJobManager(),
    )

    routes = set()
    for route in app.router.routes():
        routes.add((route.method, route.resource.canonical))

    assert ("GET", "/health") in routes
    assert ("POST", "/experiments") in routes
    assert ("POST", "/experiments/{experiment_id}/start") in routes
    assert ("POST", "/device-commands") in routes
    assert ("GET", "/jobs") in routes
