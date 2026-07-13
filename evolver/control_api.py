"""Local HTTP API for the integrated eVOLVER control plane."""

from __future__ import absolute_import

from aiohttp import web

from .control_plane import ControlPlaneError
from .maintenance_jobs import MaintenanceJobError
from .messages import MessageValidationError
from .runner_manager import RunnerManagerError


try:
    CONTROL_PLANE_KEY = web.AppKey("control_plane", object)
    RUNNER_MANAGER_KEY = web.AppKey("runner_manager", object)
    JOB_MANAGER_KEY = web.AppKey("job_manager", object)
except AttributeError:
    CONTROL_PLANE_KEY = "control_plane"
    RUNNER_MANAGER_KEY = "runner_manager"
    JOB_MANAGER_KEY = "job_manager"


def create_control_plane_app(
    control_plane,
    runner_manager=None,
    job_manager=None,
):
    app = web.Application()
    app[CONTROL_PLANE_KEY] = control_plane
    app[RUNNER_MANAGER_KEY] = runner_manager
    app[JOB_MANAGER_KEY] = job_manager

    app.router.add_get("/health", _health)
    app.router.add_get("/experiments", _list_experiments)
    app.router.add_post("/experiments", _create_experiment)
    app.router.add_post(
        "/experiments/{experiment_id}/start",
        _start_experiment,
    )
    app.router.add_post(
        "/experiments/{experiment_id}/pause",
        _pause_experiment,
    )
    app.router.add_post(
        "/experiments/{experiment_id}/resume",
        _resume_experiment,
    )
    app.router.add_post("/experiments/{experiment_id}/stop", _stop_experiment)
    app.router.add_post("/device-commands", _device_command)
    app.router.add_get("/jobs", _list_jobs)
    return app


async def _health(request):
    return _json({"ok": True, "service": "evolver-controld"})


async def _list_experiments(request):
    control_plane = request.app[CONTROL_PLANE_KEY]
    return _json({"experiments": list(control_plane.experiments.values())})


async def _create_experiment(request):
    control_plane = request.app[CONTROL_PLANE_KEY]
    try:
        body = await _read_json(request)
        experiment_id = body.pop("experiment_id", None)
        return _json(
            {
                "experiment": control_plane.create_experiment(
                    body,
                    experiment_id=experiment_id,
                )
            },
            status=201,
        )
    except _API_ERRORS as exc:
        return _error(exc)


async def _start_experiment(request):
    control_plane = request.app[CONTROL_PLANE_KEY]
    runner_manager = request.app[RUNNER_MANAGER_KEY]
    try:
        body = await _read_json(request)
        runner_spec = body.get("runner", body)
        runner_spec = start_runner_if_requested(
            request.match_info["experiment_id"],
            runner_spec,
            runner_manager,
        )
        experiment = control_plane.start_experiment(
            request.match_info["experiment_id"],
            runner_spec,
        )
        return _json({"experiment": experiment})
    except _API_ERRORS as exc:
        return _error(exc)


def start_runner_if_requested(experiment_id, runner_spec, runner_manager):
    if runner_manager is None:
        return runner_spec
    if not isinstance(runner_spec, dict):
        raise MessageValidationError("runner spec must be a JSON object")
    if runner_spec.get("kind") != "dpu_subprocess":
        return runner_spec

    dpu_dir = runner_spec.get("dpu_dir")
    if not dpu_dir:
        raise MessageValidationError("dpu_subprocess runner requires dpu_dir")

    runner_manager.start_dpu_runner(
        experiment_id,
        dpu_dir,
        ip_address=runner_spec.get("ip_address"),
        experiment_dir=runner_spec.get("experiment_dir"),
        extra_args=runner_spec.get("extra_args"),
        env=runner_spec.get("env"),
    )
    status = runner_manager.runner_status(experiment_id)
    status["kind"] = "dpu_subprocess"
    return status


async def _pause_experiment(request):
    control_plane = request.app[CONTROL_PLANE_KEY]
    try:
        body = await _read_json(request, allow_empty=True)
        experiment = control_plane.pause_experiment(
            request.match_info["experiment_id"],
            reason=body.get("reason"),
        )
        return _json({"experiment": experiment})
    except _API_ERRORS as exc:
        return _error(exc)


async def _resume_experiment(request):
    control_plane = request.app[CONTROL_PLANE_KEY]
    try:
        experiment = control_plane.resume_experiment(
            request.match_info["experiment_id"]
        )
        return _json({"experiment": experiment})
    except _API_ERRORS as exc:
        return _error(exc)


async def _stop_experiment(request):
    control_plane = request.app[CONTROL_PLANE_KEY]
    try:
        body = await _read_json(request, allow_empty=True)
        experiment = control_plane.stop_experiment(
            request.match_info["experiment_id"],
            reason=body.get("reason"),
        )
        return _json({"experiment": experiment})
    except _API_ERRORS as exc:
        return _error(exc)


async def _device_command(request):
    control_plane = request.app[CONTROL_PLANE_KEY]
    try:
        body = await _read_json(request)
        result = control_plane.request_device_command(body)
        return _json({"result": result})
    except _API_ERRORS as exc:
        return _error(exc)


async def _list_jobs(request):
    job_manager = request.app[JOB_MANAGER_KEY]
    if job_manager is None:
        return _json({"jobs": []})
    return _json({"jobs": job_manager.list_jobs()})


async def _read_json(request, allow_empty=False):
    if allow_empty and not request.can_read_body:
        return {}
    try:
        body = await request.json()
    except Exception:
        if allow_empty:
            return {}
        raise MessageValidationError("request body must be JSON")
    if not isinstance(body, dict):
        raise MessageValidationError("request body must be a JSON object")
    return body


def _json(payload, status=200):
    return web.json_response(payload, status=status)


def _error(exc):
    return _json({"error": str(exc)}, status=400)


_API_ERRORS = (
    ControlPlaneError,
    MaintenanceJobError,
    MessageValidationError,
    RunnerManagerError,
    ValueError,
)
