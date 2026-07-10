"""Tests for desktop virtual eVOLVER output mode."""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from evolver import evolver_server


def _conf(fields_expected_incoming=17):
    return {
        "experimental_params": {
            "od_90": {"fields_expected_incoming": fields_expected_incoming},
            "od_135": {"fields_expected_incoming": fields_expected_incoming},
            "temp": {"fields_expected_incoming": fields_expected_incoming},
        }
    }


def test_virtual_output_mode_env(monkeypatch):
    monkeypatch.delenv("EVOLVER_OUTPUT_MODE", raising=False)
    assert evolver_server.is_virtual_output_enabled() is False

    monkeypatch.setenv("EVOLVER_OUTPUT_MODE", "virtual")
    assert evolver_server.is_virtual_output_enabled() is True


def test_virtual_broadcast_data_uses_computer_branch_samples():
    data = evolver_server.virtual_broadcast_data(_conf())

    assert set(data) == {"od_90", "od_135", "temp"}
    assert data["od_135"][0:4] == ["404", "405", "405", "405"]
    assert data["od_90"][0] == "45294"
    assert data["temp"][0] == "1949"
    assert len(data["od_135"]) == 16
    assert len(data["od_90"]) == 16
    assert len(data["temp"]) == 16


def test_virtual_broadcast_data_matches_configured_field_count():
    data = evolver_server.virtual_broadcast_data(_conf(fields_expected_incoming=5))

    assert len(data["od_135"]) == 4
    assert len(data["od_90"]) == 4
    assert len(data["temp"]) == 4


def test_run_virtual_commands_drains_queue():
    evolver_server.evolver_conf = _conf()
    evolver_server.command_queue = [
        {"param": "od_90", "value": "1000", "type": evolver_server.RECURRING}
    ]

    loop = asyncio.new_event_loop()
    try:
        data = loop.run_until_complete(evolver_server.run_virtual_commands())
    finally:
        loop.close()

    assert evolver_server.command_queue == []
    assert "od_90" in data
