"""Runtime path helpers shared by local eVOLVER service entrypoints."""

from __future__ import absolute_import

import os


def default_data_dir():
    if os.environ.get("EVOLVER_DATA_DIR"):
        return os.environ["EVOLVER_DATA_DIR"]
    if os.environ.get("XDG_STATE_HOME"):
        return os.path.join(os.environ["XDG_STATE_HOME"], "evolver")
    if os.environ.get("HOME"):
        return os.path.join(os.environ["HOME"], ".local", "state", "evolver")
    return os.path.abspath(".evolver-state")
