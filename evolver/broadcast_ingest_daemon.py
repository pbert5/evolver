"""Runnable raw-data ingestion daemon for existing eVOLVER broadcasts."""

from __future__ import absolute_import

import argparse
import os

import socketio

from .broadcast_ingest import BroadcastIngestor
from .data_service import LocalDataService
from .runtime_paths import default_data_dir


DEFAULT_HARDWARE_URL = "http://127.0.0.1:8081"
DEFAULT_NAMESPACE = "/dpu-evolver"


def create_client(
    data_dir=None,
    server_url=DEFAULT_HARDWARE_URL,
    machine_id=None,
    namespace=DEFAULT_NAMESPACE,
    client=None,
):
    data_service = LocalDataService(data_dir or default_data_dir())
    ingestor = BroadcastIngestor(data_service)
    client = client or socketio.Client()

    @client.on("broadcast", namespace=namespace)
    def broadcast(data):
        ingestor.ingest(data, machine_id=machine_id)

    return client


def run_ingest(
    data_dir=None,
    server_url=DEFAULT_HARDWARE_URL,
    machine_id=None,
    namespace=DEFAULT_NAMESPACE,
    client=None,
):
    client = create_client(
        data_dir=data_dir,
        server_url=server_url,
        machine_id=machine_id,
        namespace=namespace,
        client=client,
    )
    client.connect(server_url, namespaces=[namespace])
    client.wait()


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Persist eVOLVER broadcasts as raw data streams.",
    )
    parser.add_argument(
        "--server-url",
        default=os.environ.get("EVOLVER_HARDWARE_URL", DEFAULT_HARDWARE_URL),
    )
    parser.add_argument("--data-dir", default=default_data_dir())
    parser.add_argument(
        "--machine-id",
        default=os.environ.get("EVOLVER_MACHINE_ID"),
    )
    parser.add_argument("--namespace", default=DEFAULT_NAMESPACE)
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    run_ingest(
        data_dir=args.data_dir,
        server_url=args.server_url,
        machine_id=args.machine_id,
        namespace=args.namespace,
    )


if __name__ == "__main__":
    main()
