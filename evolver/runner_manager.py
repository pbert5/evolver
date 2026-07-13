"""Subprocess runner management for isolated DPU experiment execution."""

from __future__ import absolute_import

import os
import signal
import subprocess
import sys


RUNNER_STARTING = "starting"
RUNNER_RUNNING = "running"
RUNNER_EXITED = "exited"
RUNNER_STOPPED = "stopped"


class RunnerManagerError(Exception):
    pass


class RunnerStateError(RunnerManagerError):
    pass


class DpuRunnerManager(object):
    """Launch and track current DPU scripts as isolated subprocesses."""

    def __init__(self, python_executable=None, popen_factory=None):
        self.python_executable = python_executable or sys.executable
        self.popen_factory = popen_factory or subprocess.Popen
        self.runners = {}

    def start_dpu_runner(
        self,
        experiment_id,
        dpu_dir,
        ip_address=None,
        experiment_dir=None,
        extra_args=None,
        env=None,
    ):
        if experiment_id in self.runners:
            runner = self.runners[experiment_id]
            if runner["process"].poll() is None:
                raise RunnerStateError(
                    "runner already active for experiment: " + experiment_id
                )

        script_path = os.path.join(
            os.path.abspath(dpu_dir),
            "experiment",
            "template",
            "eVOLVER.py",
        )
        if not os.path.exists(script_path):
            raise RunnerManagerError("DPU script not found: " + script_path)

        argv = [self.python_executable, script_path]
        if ip_address:
            argv.extend(["--ip-address", ip_address])
        if experiment_dir:
            argv.extend(["--experiment-dir", experiment_dir])
        if extra_args:
            argv.extend(list(extra_args))

        process_env = os.environ.copy()
        if env:
            process_env.update(env)

        process = self.popen_factory(
            argv,
            cwd=os.path.abspath(dpu_dir),
            env=process_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        record = {
            "experiment_id": experiment_id,
            "argv": argv,
            "cwd": os.path.abspath(dpu_dir),
            "process": process,
            "state": RUNNER_RUNNING,
        }
        self.runners[experiment_id] = record
        return dict(record)

    def runner_status(self, experiment_id):
        runner = self._runner(experiment_id)
        returncode = runner["process"].poll()
        if returncode is None:
            state = RUNNER_RUNNING
        elif runner["state"] == RUNNER_STOPPED:
            state = RUNNER_STOPPED
        else:
            state = RUNNER_EXITED
        runner["state"] = state
        return {
            "experiment_id": experiment_id,
            "state": state,
            "returncode": returncode,
            "argv": list(runner["argv"]),
            "cwd": runner["cwd"],
        }

    def interrupt_runner(self, experiment_id):
        runner = self._runner(experiment_id)
        process = runner["process"]
        if process.poll() is None:
            process.send_signal(signal.SIGINT)
        return self.runner_status(experiment_id)

    def stop_runner(self, experiment_id, timeout=5):
        runner = self._runner(experiment_id)
        process = runner["process"]
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=timeout)
            except TypeError:
                process.wait()
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        runner["state"] = RUNNER_STOPPED
        return self.runner_status(experiment_id)

    def _runner(self, experiment_id):
        try:
            return self.runners[experiment_id]
        except KeyError:
            raise RunnerStateError("unknown runner: " + str(experiment_id))
