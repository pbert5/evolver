"""Maintenance job coordination for controlled one-shot operations."""

from __future__ import absolute_import

import uuid

from .messages import EVENT_JOB_STATUS
from .messages import MessageValidationError
from .messages import make_envelope


JOB_PENDING_AUTHORIZATION = "pending_authorization"
JOB_QUEUED = "queued"
JOB_RUNNING = "running"
JOB_SUCCEEDED = "succeeded"
JOB_FAILED = "failed"
JOB_CANCELLED = "cancelled"


class MaintenanceJobError(Exception):
    pass


class InvalidJobStateError(MaintenanceJobError):
    pass


class MaintenanceJobManager(object):
    """Track authorization and execution state for maintenance jobs."""

    def __init__(self, data_service=None, producer="evolver-controld"):
        self.data_service = data_service
        self.producer = producer
        self.jobs = {}

    def create_job(
        self,
        kind,
        payload,
        job_id=None,
        requires_authorization=True,
    ):
        if not isinstance(kind, str) or not kind:
            raise MessageValidationError("job kind must be a non-empty string")
        if not isinstance(payload, dict):
            raise MessageValidationError("job payload must be a dictionary")

        job_id = job_id or str(uuid.uuid4())
        state = (
            JOB_PENDING_AUTHORIZATION
            if requires_authorization
            else JOB_QUEUED
        )
        record = {
            "id": job_id,
            "kind": kind,
            "payload": dict(payload),
            "state": state,
            "result": None,
            "error": None,
        }
        self.jobs[job_id] = record
        self._record_status(record)
        return dict(record)

    def authorize_job(self, job_id, approved, reason=None):
        job = self._job(job_id)
        if job["state"] != JOB_PENDING_AUTHORIZATION:
            raise InvalidJobStateError(
                "job is not pending authorization: " + job_id
            )
        if approved:
            job["state"] = JOB_QUEUED
        else:
            job["state"] = JOB_CANCELLED
            job["error"] = reason or "authorization rejected"
        self._record_status(job)
        return dict(job)

    def run_job(self, job_id, worker):
        job = self._job(job_id)
        if job["state"] != JOB_QUEUED:
            raise InvalidJobStateError("job is not queued: " + job_id)

        job["state"] = JOB_RUNNING
        self._record_status(job)
        try:
            job["result"] = worker(dict(job["payload"]))
        except Exception as exc:
            job["state"] = JOB_FAILED
            job["error"] = str(exc)
            self._record_status(job)
            return dict(job)

        job["state"] = JOB_SUCCEEDED
        self._record_status(job)
        return dict(job)

    def cancel_job(self, job_id, reason=None):
        job = self._job(job_id)
        if job["state"] in [JOB_SUCCEEDED, JOB_FAILED, JOB_CANCELLED]:
            raise InvalidJobStateError("job is already terminal: " + job_id)
        job["state"] = JOB_CANCELLED
        job["error"] = reason or "cancelled"
        self._record_status(job)
        return dict(job)

    def list_jobs(self):
        return [dict(job) for job in self.jobs.values()]

    def _job(self, job_id):
        try:
            return self.jobs[job_id]
        except KeyError:
            raise MaintenanceJobError("unknown job: " + str(job_id))

    def _record_status(self, job):
        if self.data_service is None:
            return None
        payload = {
            "job_id": job["id"],
            "kind": job["kind"],
            "state": job["state"],
            "result": job["result"],
            "error": job["error"],
        }
        envelope = make_envelope(EVENT_JOB_STATUS, payload, self.producer)
        return self.data_service.append_record(
            "jobs/{0}/events".format(job["id"]),
            envelope,
        )
