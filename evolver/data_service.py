"""Local JSONL data service for raw and experiment records."""

from __future__ import absolute_import

import json
import os
import re

from .messages import EVENT_MACHINE_RAW_MEASUREMENT
from .messages import MessageValidationError
from .messages import validate_envelope


_STREAM_PART_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


class LocalDataService(object):
    """Append-only local storage used by the phase-1 integrated services."""

    def __init__(self, root_dir):
        self.root_dir = os.path.abspath(root_dir)

    def append_raw_measurement(self, envelope):
        validate_envelope(
            envelope,
            allowed_kinds=[EVENT_MACHINE_RAW_MEASUREMENT],
        )
        machine_id = envelope["payload"]["machine_id"]
        return self.append_record(
            "machines/{0}/raw".format(machine_id),
            envelope,
        )

    def append_experiment_event(self, experiment_id, envelope):
        if not isinstance(experiment_id, str) or not experiment_id:
            raise MessageValidationError(
                "experiment_id must be a non-empty string"
            )
        validate_envelope(envelope)
        return self.append_record(
            "experiments/{0}/events".format(experiment_id),
            envelope,
        )

    def append_record(self, stream, envelope):
        validate_envelope(envelope)
        path = self.record_path(stream)
        directory = os.path.dirname(path)
        if not os.path.isdir(directory):
            os.makedirs(directory)

        with open(path, "a") as handle:
            handle.write(json.dumps(envelope, sort_keys=True))
            handle.write("\n")
        return path

    def read_records(self, stream):
        path = self.record_path(stream)
        if not os.path.exists(path):
            return []

        records = []
        with open(path) as handle:
            for line in handle:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
        return records

    def record_path(self, stream):
        parts = stream.split("/")
        if not parts or any(not part for part in parts):
            raise MessageValidationError(
                "stream must contain non-empty path parts"
            )
        for part in parts:
            if part in [".", ".."]:
                raise MessageValidationError(
                    "unsafe stream path part: " + part
                )
            if not _STREAM_PART_RE.match(part):
                raise MessageValidationError(
                    "unsafe stream path part: " + part
                )
        return os.path.join(self.root_dir, "streams", *parts) + ".jsonl"
