"""Integration tests for the virtual eVOLVER server."""

import os
import queue
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import socketio


ROOT = Path(__file__).resolve().parents[1]
SERVER_DIR = ROOT / "evolver"


def _free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _reader(proc, lines):
    assert proc.stdout is not None
    for line in proc.stdout:
        lines.put(line.rstrip())


def _copy_state(tmp_path):
    state_dir = tmp_path / "virtual-state"
    state_dir.mkdir()
    for name in ("conf.yml", "calibrations.json", "evolver-config.json", "test_device.json"):
        src = SERVER_DIR / name
        if src.exists():
            dst = state_dir / name
            shutil.copy2(src, dst)
            dst.chmod(0o600)
    return state_dir


def _start_virtual_server(tmp_path):
    port = _free_port()
    state_dir = _copy_state(tmp_path)
    env = os.environ.copy()
    env.update(
        {
            "EVOLVER_OUTPUT_MODE": "virtual",
            "EVOLVER_BIND_HOST": "127.0.0.1",
            "EVOLVER_IP": "127.0.0.1",
            "EVOLVER_PORT": str(port),
            "EVOLVER_BROADCAST_TIMING": "0.25",
            "EVOLVER_DATA_DIR": str(state_dir),
            "PYTHONPATH": "{0}{1}{2}".format(
                ROOT,
                os.pathsep,
                env.get("PYTHONPATH", ""),
            ),
        }
    )
    proc = subprocess.Popen(
        [sys.executable, str(SERVER_DIR / "evolver.py")],
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    lines = queue.Queue()
    thread = threading.Thread(target=_reader, args=(proc, lines), daemon=True)
    thread.start()
    return proc, lines, port


def _stop(proc):
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


def _wait_for_server(proc, lines, port):
    collected = []
    deadline = time.time() + 15
    while time.time() < deadline:
        if proc.poll() is not None:
            while True:
                try:
                    collected.append(lines.get_nowait())
                except queue.Empty:
                    break
            raise AssertionError(
                "virtual server exited early with {0}:\n{1}".format(
                    proc.returncode,
                    "\n".join(collected),
                )
            )
        try:
            line = lines.get(timeout=0.25)
        except queue.Empty:
            continue
        collected.append(line)
        if "Running on" in line and str(port) in line:
            return
    raise AssertionError(
        "virtual server did not start on port {0}:\n{1}".format(
            port,
            "\n".join(collected),
        )
    )


def test_virtual_server_socketio_round_trip(tmp_path):
    proc, lines, port = _start_virtual_server(tmp_path)
    try:
        _wait_for_server(proc, lines, port)

        events = queue.Queue()
        client = socketio.Client(reconnection=False, request_timeout=3)

        @client.event(namespace="/dpu-evolver")
        def connect():
            events.put(("connect", None))

        @client.on("broadcast", namespace="/dpu-evolver")
        def broadcast(data):
            events.put(("broadcast", data))

        @client.on("activecalibrations", namespace="/dpu-evolver")
        def activecalibrations(data):
            events.put(("activecalibrations", data))

        @client.on("commandbroadcast", namespace="/dpu-evolver")
        def commandbroadcast(data):
            events.put(("commandbroadcast", data))

        client.connect(
            "http://127.0.0.1:{0}".format(port),
            namespaces=["/dpu-evolver"],
            wait_timeout=5,
        )
        client.emit("getactivecal", {}, namespace="/dpu-evolver")
        client.emit(
            "command",
            {
                "param": "stir",
                "value": [4] * 16,
                "immediate": True,
                "recurring": True,
            },
            namespace="/dpu-evolver",
        )

        seen = {}
        broadcasts = []
        deadline = time.time() + 15
        while time.time() < deadline and not (
            "connect" in seen
            and "activecalibrations" in seen
            and "commandbroadcast" in seen
            and broadcasts
        ):
            try:
                name, data = events.get(timeout=0.25)
            except queue.Empty:
                continue
            seen.setdefault(name, data)
            if name == "broadcast":
                broadcasts.append(data)

        assert "connect" in seen
        assert len(seen["activecalibrations"]) >= 1
        assert seen["commandbroadcast"]["value"] == [4] * 16
        assert broadcasts[-1]["data"]["od_135"][0] == "404"
        client.disconnect()
    finally:
        _stop(proc)
