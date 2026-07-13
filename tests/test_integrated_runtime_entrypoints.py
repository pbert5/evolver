from evolver.broadcast_ingest_daemon import create_client
from evolver.control_api import start_runner_if_requested
from evolver.control_daemon import SocketIOHardwareClient
from evolver.messages import MessageValidationError


class FakeSocketClient(object):
    def __init__(self):
        self.connected = False
        self.connects = []
        self.emits = []
        self.handlers = {}

    def connect(self, server_url, namespaces=None):
        self.connected = True
        self.connects.append((server_url, namespaces))

    def emit(self, event, data, namespace=None):
        self.emits.append((event, data, namespace))

    def on(self, event, namespace=None):
        def decorator(handler):
            self.handlers[(event, namespace)] = handler
            return handler

        return decorator


class FakeRunnerManager(object):
    def __init__(self):
        self.started = []

    def start_dpu_runner(
        self,
        experiment_id,
        dpu_dir,
        ip_address=None,
        experiment_dir=None,
        extra_args=None,
        env=None,
    ):
        self.started.append(
            {
                "experiment_id": experiment_id,
                "dpu_dir": dpu_dir,
                "ip_address": ip_address,
                "experiment_dir": experiment_dir,
                "extra_args": extra_args,
                "env": env,
            }
        )

    def runner_status(self, experiment_id):
        return {
            "experiment_id": experiment_id,
            "state": "running",
            "argv": ["python", "eVOLVER.py"],
            "cwd": "/workspace/dpu",
            "returncode": None,
        }


def test_socketio_hardware_client_forwards_validated_command():
    socket_client = FakeSocketClient()
    hardware = SocketIOHardwareClient(
        server_url="http://server:8081",
        client=socket_client,
    )

    result = hardware.send_command({"param": "stir", "value": ["8"] * 16})

    assert result["accepted"] is True
    assert socket_client.connects == [
        ("http://server:8081", ["/dpu-evolver"]),
    ]
    assert socket_client.emits == [
        ("command", {"param": "stir", "value": ["8"] * 16}, "/dpu-evolver"),
    ]


def test_start_runner_if_requested_launches_dpu_subprocess_spec():
    runner_manager = FakeRunnerManager()

    runner_spec = start_runner_if_requested(
        "exp-1",
        {
            "kind": "dpu_subprocess",
            "dpu_dir": "/workspace/dpu",
            "ip_address": "127.0.0.1",
            "experiment_dir": "/tmp/exp-1",
            "extra_args": ["--exit-after-broadcasts", "1"],
            "env": {"EXAMPLE": "1"},
        },
        runner_manager,
    )

    assert runner_manager.started == [
        {
            "experiment_id": "exp-1",
            "dpu_dir": "/workspace/dpu",
            "ip_address": "127.0.0.1",
            "experiment_dir": "/tmp/exp-1",
            "extra_args": ["--exit-after-broadcasts", "1"],
            "env": {"EXAMPLE": "1"},
        }
    ]
    assert runner_spec["kind"] == "dpu_subprocess"
    assert runner_spec["state"] == "running"
    assert "returncode" in runner_spec


def test_start_runner_if_requested_requires_dpu_dir():
    try:
        start_runner_if_requested(
            "exp-1",
            {"kind": "dpu_subprocess"},
            FakeRunnerManager(),
        )
    except MessageValidationError as exc:
        assert "dpu_dir" in str(exc)
    else:
        raise AssertionError("expected MessageValidationError")


def test_broadcast_ingest_daemon_registers_broadcast_handler(tmp_path):
    socket_client = FakeSocketClient()
    create_client(
        data_dir=str(tmp_path),
        machine_id="machine-1",
        client=socket_client,
    )

    handler = socket_client.handlers[("broadcast", "/dpu-evolver")]
    handler({"data": {"temp": ["b", "30.1"]}, "timestamp": 0})

    path = tmp_path / "streams" / "machines" / "machine-1" / "raw.jsonl"
    assert path.exists()
    assert "machine.measurement.raw" in path.read_text()
