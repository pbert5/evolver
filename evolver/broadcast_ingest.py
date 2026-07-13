"""Convert existing eVOLVER broadcasts into durable raw-data records."""

from __future__ import absolute_import

import datetime

from .messages import MessageValidationError
from .messages import make_raw_measurement


class BroadcastIngestor(object):
    """Persist hardware-server broadcast payloads through LocalDataService."""

    def __init__(self, data_service, producer="evolver-hardwared"):
        self.data_service = data_service
        self.producer = producer

    def ingest(self, broadcast, machine_id=None):
        envelope = broadcast_to_raw_measurement(
            broadcast,
            producer=self.producer,
            machine_id=machine_id,
        )
        self.data_service.append_raw_measurement(envelope)
        return envelope


def broadcast_to_raw_measurement(broadcast, producer, machine_id=None):
    """Translate the current Socket.IO broadcast shape into a raw envelope."""
    if not isinstance(broadcast, dict):
        raise MessageValidationError("broadcast must be a dictionary")

    measurements = broadcast.get("data")
    if not isinstance(measurements, dict) or not measurements:
        raise MessageValidationError("broadcast data must be a non-empty dict")

    selected_machine_id = (
        machine_id
        or broadcast.get("machine_id")
        or broadcast.get("device_id")
        or _machine_id_from_ip(broadcast.get("ip"))
    )
    if not selected_machine_id:
        raise MessageValidationError("broadcast must identify a machine")

    metadata = {
        "source": "socketio-broadcast",
    }
    if "ip" in broadcast:
        metadata["ip"] = broadcast["ip"]
    if "config" in broadcast:
        metadata["config"] = broadcast["config"]
    if "timestamp" in broadcast:
        metadata["server_timestamp"] = broadcast["timestamp"]

    return make_raw_measurement(
        selected_machine_id,
        measurements,
        producer=producer,
        observed_at=_observed_at(broadcast),
        metadata=metadata,
    )


def _machine_id_from_ip(ip_address):
    if not isinstance(ip_address, str) or not ip_address:
        return None
    return "evolver-" + ip_address.replace(".", "-").replace(":", "-")


def _observed_at(broadcast):
    timestamp = broadcast.get("timestamp")
    if isinstance(timestamp, (int, float)):
        observed = datetime.datetime.fromtimestamp(
            timestamp,
            datetime.timezone.utc,
        )
        return (
            observed.replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )
    if isinstance(timestamp, str) and timestamp:
        return timestamp
    return None
