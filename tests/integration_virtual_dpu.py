#!/usr/bin/env python3
"""Run a bounded virtual eVOLVER + DPU communication smoke test."""

import argparse
import os
import queue
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path


ROOT = Path(os.environ.get("EVOLVER_REPO_ROOT", Path.cwd())).resolve()
DEFAULT_DPU_DIR = ROOT.parent / "dpu"


def _free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _reader(name, proc, events, lines):
    assert proc.stdout is not None
    for line in proc.stdout:
        text = line.rstrip()
        tagged = "[{0}] {1}".format(name, text)
        lines.append(tagged)
        events.put(tagged)


def _start(name, cmd, cwd, env, events, lines):
    proc = subprocess.Popen(
        cmd,
        cwd=str(cwd),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    thread = threading.Thread(target=_reader, args=(name, proc, events, lines), daemon=True)
    thread.start()
    return proc


def _terminate(proc):
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


def run_integration(dpu_dir=DEFAULT_DPU_DIR, timeout=120, stream=True):
    dpu_dir = Path(dpu_dir).resolve()
    if not (dpu_dir / "flake.nix").exists():
        raise AssertionError("DPU checkout not found at {0}".format(dpu_dir))

    nix = shutil.which("nix")
    if nix is None:
        raise AssertionError("nix not found on PATH")

    port = _free_port()
    events = queue.Queue()
    lines = []
    server = None
    dpu = None

    with tempfile.TemporaryDirectory(prefix="evolver-virtual-dpu-") as tmp:
        tmp_path = Path(tmp)
        server_env = os.environ.copy()
        server_env.update(
            {
                "EVOLVER_OUTPUT_MODE": "virtual",
                "EVOLVER_BIND_HOST": "127.0.0.1",
                "EVOLVER_PORT": str(port),
                "EVOLVER_BROADCAST_TIMING": "1",
                "EVOLVER_DATA_DIR": str(tmp_path / "server-state"),
            }
        )
        dpu_env = os.environ.copy()
        dpu_env.update(
            {
                "EVOLVER_PORT": str(port),
                "EVOLVER_DPU_BYPASS_PROMPTS": "1",
                "EVOLVER_DPU_EXIT_AFTER_BROADCASTS": "1",
                "EVOLVER_DPU_EXP_DIR": str(tmp_path / "dpu-experiment"),
                "EVOLVER_DPU_STATE_DIR": str(tmp_path / "dpu-state"),
                "EVOLVER_DPU_SOCKETIO_CLIENT": "modern",
                "EVOLVER_DPU_COMMUNICATION_SMOKE_ONLY": "1",
            }
        )

        try:
            server = _start(
                "server",
                [nix, "run", "-L", ".#run-virtual-evolver"],
                ROOT,
                server_env,
                events,
                lines,
            )

            deadline = time.time() + timeout
            server_ready = False
            dpu_connected = False
            broadcast_seen = False

            while time.time() < deadline:
                remaining = max(0.1, deadline - time.time())
                try:
                    line = events.get(timeout=min(1, remaining))
                except queue.Empty:
                    if server.poll() is not None:
                        raise AssertionError("virtual server exited early with {0}".format(server.returncode))
                    if dpu is not None and dpu.poll() not in (None, 0):
                        raise AssertionError("DPU exited early with {0}".format(dpu.returncode))
                    continue

                if stream:
                    print(line, flush=True)

                if "[server]" in line and "Running on" in line and str(port) in line:
                    server_ready = True
                    dpu = _start(
                        "dpu",
                        [
                            nix,
                            "run",
                            "-L",
                            ".#run-dpu",
                            "--",
                            "-i",
                            "127.0.0.1",
                            "--bypass-prompts",
                            "--exit-after-broadcasts",
                            "1",
                            "--experiment-dir",
                            str(tmp_path / "dpu-experiment"),
                            "--socketio-client",
                            "modern",
                            "--communication-smoke-only",
                            "-q",
                        ],
                        dpu_dir,
                        dpu_env,
                        events,
                        lines,
                    )

                if "[dpu]" in line and "Connected to eVOLVER as client" in line:
                    dpu_connected = True
                if "[dpu]" in line and "Broadcast received from eVOLVER" in line:
                    broadcast_seen = True
                if dpu is not None and dpu.poll() == 0 and dpu_connected and broadcast_seen:
                    return lines

            raise AssertionError(
                "timed out waiting for communication; server_ready={0}, dpu_connected={1}, broadcast_seen={2}".format(
                    server_ready, dpu_connected, broadcast_seen
                )
            )
        finally:
            if dpu is not None:
                _terminate(dpu)
            if server is not None:
                _terminate(server)


def test_virtual_dpu_smoke():
    run_integration(stream=False)


def main():
    parser = argparse.ArgumentParser(description="Run the virtual eVOLVER + DPU smoke test.")
    parser.add_argument("--dpu-dir", default=str(DEFAULT_DPU_DIR), help="Path to the DPU checkout.")
    parser.add_argument("--timeout", type=int, default=120, help="Seconds to wait for communication.")
    args = parser.parse_args()

    try:
        run_integration(dpu_dir=args.dpu_dir, timeout=args.timeout, stream=True)
    except AssertionError as exc:
        print("FAILED: {0}".format(exc), file=sys.stderr)
        return 1
    print("PASS: virtual server and DPU exchanged a broadcast")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
