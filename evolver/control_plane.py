"""Minimal control-plane coordinator for local eVOLVER services."""

from __future__ import absolute_import

import uuid

from .messages import EVENT_EXPERIMENT_RUNNER_ACTION
from .messages import MessageValidationError
from .messages import make_envelope
from .messages import make_experiment_status
from .messages import validate_device_command_request
from .messages import validate_envelope
from .messages import validate_experiment_request


STATE_CREATED = "created"
STATE_RUNNING = "running"
STATE_PAUSED = "paused"
STATE_STOPPED = "stopped"
STATE_FAILED = "failed"


class ControlPlaneError(Exception):
    pass


class ExperimentNotFoundError(ControlPlaneError):
    pass


class InvalidTransitionError(ControlPlaneError):
    pass


class ControlPlane(object):
    """Coordinate experiment lifecycle without owning hardware transport."""

    def __init__(
        self,
        hardware_client,
        data_service=None,
        producer="evolver-controld",
    ):
        self.hardware_client = hardware_client
        self.data_service = data_service
        self.producer = producer
        self.experiments = {}

    def create_experiment(self, request, experiment_id=None):
        request = validate_experiment_request(request)
        experiment_id = experiment_id or str(uuid.uuid4())
        record = {
            "id": experiment_id,
            "state": STATE_CREATED,
            "request": request,
            "runner": None,
        }
        self.experiments[experiment_id] = record
        self._record_status(experiment_id, STATE_CREATED)
        return dict(record)

    def start_experiment(self, experiment_id, runner_spec):
        record = self._get_experiment(experiment_id)
        if record["state"] not in [STATE_CREATED, STATE_PAUSED]:
            raise InvalidTransitionError(
                "cannot start experiment from state: " + record["state"]
            )
        if not isinstance(runner_spec, dict):
            raise MessageValidationError("runner_spec must be a dictionary")

        record["runner"] = dict(runner_spec)
        record["state"] = STATE_RUNNING
        self._record_status(experiment_id, STATE_RUNNING)
        return dict(record)

    def pause_experiment(self, experiment_id, reason=None):
        return self._transition(
            experiment_id,
            [STATE_RUNNING],
            STATE_PAUSED,
            reason,
        )

    def resume_experiment(self, experiment_id):
        record = self._get_experiment(experiment_id)
        if record["state"] != STATE_PAUSED:
            raise InvalidTransitionError(
                "cannot resume experiment from state: " + record["state"]
            )
        record["state"] = STATE_RUNNING
        self._record_status(experiment_id, STATE_RUNNING)
        return dict(record)

    def stop_experiment(self, experiment_id, reason=None):
        return self._transition(
            experiment_id,
            [STATE_CREATED, STATE_RUNNING, STATE_PAUSED],
            STATE_STOPPED,
            reason,
        )

    def fail_experiment(self, experiment_id, reason):
        return self._transition(
            experiment_id,
            [STATE_CREATED, STATE_RUNNING, STATE_PAUSED],
            STATE_FAILED,
            reason,
        )

    def handle_runner_action(self, envelope):
        envelope = validate_envelope(
            envelope, allowed_kinds=[EVENT_EXPERIMENT_RUNNER_ACTION]
        )
        payload = envelope["payload"]
        action = payload.get("action")
        if action != "device_command":
            raise MessageValidationError(
                "unsupported runner action: " + str(action)
            )

        command = validate_device_command_request(payload.get("command"))
        experiment_id = command.get("experiment_id")
        if experiment_id:
            record = self._get_experiment(experiment_id)
            if record["state"] != STATE_RUNNING:
                raise InvalidTransitionError(
                    "runner command requires running experiment: "
                    + experiment_id
                )

        result = self.hardware_client.send_command(command)
        if self.data_service is not None and experiment_id:
            self.data_service.append_experiment_event(experiment_id, envelope)
        return result

    def request_device_command(self, command):
        command = validate_device_command_request(command)
        return self.hardware_client.send_command(command)

    def _transition(
        self,
        experiment_id,
        allowed_states,
        next_state,
        reason=None,
    ):
        record = self._get_experiment(experiment_id)
        if record["state"] not in allowed_states:
            raise InvalidTransitionError(
                "cannot move experiment from {0} to {1}".format(
                    record["state"], next_state
                )
            )
        record["state"] = next_state
        self._record_status(experiment_id, next_state, reason=reason)
        return dict(record)

    def _get_experiment(self, experiment_id):
        try:
            return self.experiments[experiment_id]
        except KeyError:
            raise ExperimentNotFoundError(
                "unknown experiment: " + str(experiment_id)
            )

    def _record_status(self, experiment_id, state, reason=None):
        if self.data_service is None:
            return None
        envelope = make_experiment_status(
            experiment_id, state, self.producer, reason=reason
        )
        return self.data_service.append_experiment_event(
            experiment_id,
            envelope,
        )


def make_runner_action(action, command, producer, message_id=None):
    payload = {
        "action": action,
        "command": command,
    }
    return make_envelope(
        EVENT_EXPERIMENT_RUNNER_ACTION,
        payload,
        producer,
        message_id=message_id,
    )
