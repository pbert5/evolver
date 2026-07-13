"""Runnable local control-plane daemon."""

from __future__ import absolute_import

import argparse
import os

import socketio
from aiohttp import web

from .control_api import create_control_plane_app
from .control_plane import ControlPlane
from .data_service import LocalDataService
from .maintenance_jobs import MaintenanceJobManager
from .runner_manager import DpuRunnerManager
from .runtime_paths import default_data_dir


DEFAULT_CONTROL_HOST = "127.0.0.1"
DEFAULT_CONTROL_PORT = 8082
DEFAULT_HARDWARE_URL = "http://127.0.0.1:8081"
DEFAULT_NAMESPACE = "/dpu-evolver"


class SocketIOHardwareClient(object):
    """Hardware client that forwards commands to the existing server."""

    def __init__(
        self,
        server_url=DEFAULT_HARDWARE_URL,
        namespace=DEFAULT_NAMESPACE,
        client=None,
    ):
        self.server_url = server_url
        self.namespace = namespace
        self.client = client or socketio.Client()

    def send_command(self, command):
        if not self.client.connected:
            self.client.connect(self.server_url, namespaces=[self.namespace])
        self.client.emit("command", command, namespace=self.namespace)
        return {
            "accepted": True,
            "transport": "socketio",
            "server_url": self.server_url,
            "namespace": self.namespace,
            "command": command,
        }


def create_app(
    data_dir=None,
    hardware_url=DEFAULT_HARDWARE_URL,
    hardware_client=None,
    runner_manager=None,
    job_manager=None,
):
    data_dir = data_dir or default_data_dir()
    data_service = LocalDataService(data_dir)
    hardware_client = hardware_client or SocketIOHardwareClient(hardware_url)
    runner_manager = runner_manager or DpuRunnerManager()
    job_manager = job_manager or MaintenanceJobManager(
        data_service=data_service,
    )
    control_plane = ControlPlane(
        hardware_client,
        data_service=data_service,
    )
    return create_control_plane_app(
        control_plane,
        runner_manager=runner_manager,
        job_manager=job_manager,
    )


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Run the local eVOLVER control-plane API.",
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("EVOLVER_CONTROL_HOST", DEFAULT_CONTROL_HOST),
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(
            os.environ.get("EVOLVER_CONTROL_PORT", DEFAULT_CONTROL_PORT)
        ),
    )
    parser.add_argument(
        "--data-dir",
        default=default_data_dir(),
    )
    parser.add_argument(
        "--hardware-url",
        default=os.environ.get("EVOLVER_HARDWARE_URL", DEFAULT_HARDWARE_URL),
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    app = create_app(
        data_dir=args.data_dir,
        hardware_url=args.hardware_url,
    )
    web.run_app(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
