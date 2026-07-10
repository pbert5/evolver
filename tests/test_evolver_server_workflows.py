"""Hardware-free eVOLVER server workflows with fake DPU and Arduino links."""

import asyncio
import copy
import json

import yaml

from evolver import evolver_server


class RecordingSio:
    def __init__(self):
        self.events = []
        self.attached_app = None

    def attach(self, app):
        self.attached_app = app

    async def emit(self, event, data, namespace=None):
        self.events.append(
            {
                "event": event,
                "data": data,
                "namespace": namespace,
            }
        )


class RecordingSerial:
    def __init__(self, conf, responses=None):
        self.conf = conf
        self.responses = responses or {}
        self.writes = []
        self.last_param = None
        self.reset_input_count = 0
        self.reset_output_count = 0

    def reset_input_buffer(self):
        self.reset_input_count += 1

    def reset_output_buffer(self):
        self.reset_output_count += 1

    def write(self, data):
        message = data.decode("UTF-8", errors="ignore")
        self.writes.append(message)
        for param in self.conf["experimental_params"]:
            if message.startswith(param):
                self.last_param = param
                break

    def readline(self):
        param = self.last_param
        values = self.responses.get(param)
        if values is None:
            field_count = self.conf["experimental_params"][param]["fields_expected_incoming"]
            values = [self.conf["data_response_char"]] + [
                str(i) for i in range(1, field_count)
            ]
        response = param + ",".join(values) + "," + self.conf["serial_end_incoming"]
        return response.encode("UTF-8")


class StaticResponseSerial(RecordingSerial):
    def __init__(self, conf, response):
        super().__init__(conf)
        self.response = response

    def readline(self):
        return self.response.encode("UTF-8")


def _run(coro):
    return asyncio.run(coro)


def _server_conf():
    return {
        "experimental_params": {
            "od_90": {
                "recurring": True,
                "fields_expected_outgoing": 2,
                "fields_expected_incoming": 17,
                "value": "1000",
            },
            "temp": {
                "recurring": True,
                "fields_expected_outgoing": 17,
                "fields_expected_incoming": 17,
                "value": [str(3000 + i) for i in range(16)],
                "pre": [{"param": "stir", "value": "values"}],
                "post": [{"param": "od_led", "value": ["0"] * 16}],
            },
            "stir": {
                "recurring": False,
                "fields_expected_outgoing": 17,
                "fields_expected_incoming": 17,
                "value": [str(8 + i) for i in range(16)],
            },
            "od_led": {
                "recurring": False,
                "fields_expected_outgoing": 17,
                "fields_expected_incoming": 17,
                "value": ["4095"] * 16,
            },
        },
        "serial_end_outgoing": "_!",
        "serial_end_incoming": "end",
        "serial_delay": 0,
        "recurring_command_char": "r",
        "immediate_command_char": "i",
        "echo_response_char": "e",
        "data_response_char": "b",
        "acknowledge_char": "a",
        "evolver_ip": "127.0.0.1",
        "device": "evolver-config.json",
    }


def _calibrations():
    return [
        {
            "name": "od-cal-2026",
            "calibrationType": "od",
            "fits": [
                {
                    "name": "od90-fit",
                    "active": True,
                    "params": ["od_90"],
                    "coefficients": [1, 2, 3, 4],
                },
                {
                    "name": "od135-fit",
                    "active": False,
                    "params": ["od_135"],
                    "coefficients": [5, 6, 7, 8],
                },
            ],
            "raw": [],
        },
        {
            "name": "temp-cal-2026",
            "calibrationType": "temperature",
            "fits": [
                {
                    "name": "temp-fit",
                    "active": False,
                    "params": ["temp"],
                    "coefficients": [[-0.02, 80]],
                }
            ],
            "raw": [],
        },
    ]


def _install_server_state(monkeypatch, tmp_path, conf=None):
    conf = copy.deepcopy(conf or _server_conf())
    conf_path = tmp_path / "conf.yml"
    conf_path.write_text(yaml.safe_dump(conf))
    monkeypatch.setattr(evolver_server, "LOCATION", str(tmp_path))
    monkeypatch.setattr(
        evolver_server.evolver, "conf_path", lambda: str(conf_path), raising=False
    )
    monkeypatch.setattr(evolver_server.time, "sleep", lambda _seconds: None)
    evolver_server.evolver_conf = conf
    evolver_server.command_queue = []
    return conf, conf_path


def test_dpu_command_updates_config_queues_immediate_and_rebroadcasts(monkeypatch, tmp_path):
    conf, conf_path = _install_server_state(monkeypatch, tmp_path)
    sio = RecordingSio()
    monkeypatch.setattr(evolver_server, "sio", sio)
    evolver_server.command_queue = [
        {"param": "temp", "value": ["old"] * 16, "type": evolver_server.RECURRING}
    ]

    value = ["NaN"] + [str(3200 + i) for i in range(1, 16)]
    _run(
        evolver_server.on_command(
            "dpu-1",
            {
                "param": "temp",
                "value": value,
                "immediate": True,
                "recurring": False,
                "fields_expected_outgoing": 17,
                "fields_expected_incoming": 17,
            },
        )
    )

    saved = yaml.safe_load(conf_path.read_text())
    assert saved["experimental_params"]["temp"]["value"][0] == conf["experimental_params"][
        "temp"
    ]["value"][0]
    assert saved["experimental_params"]["temp"]["value"][1] == "3201"
    assert saved["experimental_params"]["temp"]["recurring"] is False
    assert evolver_server.command_queue == [
        {"param": "temp", "value": value, "type": evolver_server.IMMEDIATE}
    ]
    assert sio.events == [
        {
            "event": "commandbroadcast",
            "data": {
                "param": "temp",
                "value": value,
                "immediate": True,
                "recurring": False,
                "fields_expected_outgoing": 17,
                "fields_expected_incoming": 17,
            },
            "namespace": "/dpu-evolver",
        }
    ]


def test_serial_communication_writes_command_ack_and_returns_arduino_data(
    monkeypatch, tmp_path
):
    conf, _conf_path = _install_server_state(monkeypatch, tmp_path)
    serial = RecordingSerial(conf)
    evolver_server.serial_connection = serial

    returned = evolver_server.serial_communication(
        "od_90", "1000", evolver_server.RECURRING
    )

    assert returned == [str(i) for i in range(1, 17)]
    assert serial.writes == ["od_90r,1000,_!", "od_90a,,_!"]
    assert serial.reset_input_count == 1
    assert serial.reset_output_count == 1


def test_serial_communication_substitutes_nan_values_for_arduino_commands(
    monkeypatch, tmp_path
):
    conf, _conf_path = _install_server_state(monkeypatch, tmp_path)
    serial = RecordingSerial(conf)
    evolver_server.serial_connection = serial

    incoming_value = ["NaN"] + [str(3300 + i) for i in range(1, 16)]
    returned = evolver_server.serial_communication(
        "temp", incoming_value, evolver_server.IMMEDIATE
    )

    assert returned == [str(i) for i in range(1, 17)]
    assert serial.writes[0].startswith("tempi,3000,3301,3302")
    assert serial.writes[1] == "tempa,,,,,,,,,,,,,,,,,_!"


def test_broadcast_processes_recurring_commands_and_emits_dpu_payload(
    monkeypatch, tmp_path
):
    conf, _conf_path = _install_server_state(monkeypatch, tmp_path)
    sio = RecordingSio()
    serial = RecordingSerial(conf)
    monkeypatch.setattr(evolver_server, "sio", sio)
    monkeypatch.setattr(evolver_server, "is_virtual_output_enabled", lambda: False)
    monkeypatch.setattr(evolver_server.time, "time", lambda: 123.45)
    evolver_server.serial_connection = serial

    _run(evolver_server.broadcast(commands_in_queue=False))

    assert evolver_server.command_queue == []
    assert [event["event"] for event in sio.events] == ["broadcast"]
    payload = sio.events[0]["data"]
    assert payload["ip"] == "127.0.0.1"
    assert payload["timestamp"] == 123.45
    assert payload["data"]["od_90"] == [str(i) for i in range(1, 17)]
    assert payload["data"]["temp"] == [str(i) for i in range(1, 17)]
    assert any(write.startswith("stiri,8,9,10") for write in serial.writes)
    assert any(write.startswith("od_ledi,0,0,0") for write in serial.writes)


def test_calibration_queries_and_active_fit_updates_round_trip_to_dpu(
    monkeypatch, tmp_path
):
    _install_server_state(monkeypatch, tmp_path)
    calibrations_path = tmp_path / evolver_server.CALIBRATIONS_FILENAME
    calibrations_path.write_text(json.dumps(_calibrations()))
    sio = RecordingSio()
    monkeypatch.setattr(evolver_server, "sio", sio)

    _run(evolver_server.on_getcalibrationnames("dpu-1", {}))
    _run(evolver_server.on_getfitnames("dpu-1", {}))
    _run(evolver_server.on_getcalibration("dpu-1", {"name": "od-cal-2026"}))
    _run(
        evolver_server.on_setactiveodcal(
            "dpu-1", {"calibration_names": ["temp-fit"]}
        )
    )
    _run(evolver_server.on_getactivecal("dpu-1", {}))

    assert sio.events[0]["event"] == "calibrationnames"
    assert sio.events[0]["data"] == [
        {"name": "od-cal-2026", "calibrationType": "od"},
        {"name": "temp-cal-2026", "calibrationType": "temperature"},
    ]
    assert sio.events[1]["event"] == "fitnames"
    assert {"name": "od90-fit", "calibrationType": "od"} in sio.events[1]["data"]
    assert sio.events[2]["event"] == "calibration"
    assert sio.events[2]["data"]["name"] == "od-cal-2026"
    assert sio.events[3]["event"] == "activecalibrations"
    assert sio.events[3]["data"][0]["name"] == "temp-cal-2026"
    assert sio.events[4]["event"] == "activecalibrations"
    assert sio.events[4]["data"][0]["name"] == "temp-cal-2026"

    saved = json.loads(calibrations_path.read_text())
    assert saved[0]["fits"][0]["active"] is False
    assert saved[1]["fits"][0]["active"] is True


def test_device_name_round_trip_uses_server_config_file(monkeypatch, tmp_path):
    _install_server_state(monkeypatch, tmp_path)
    sio = RecordingSio()
    monkeypatch.setattr(evolver_server, "sio", sio)
    device = {"deviceName": "Bench eVOLVER", "vial": 16, "status": 3}

    _run(evolver_server.on_setdevicename("dpu-1", device))
    _run(evolver_server.on_getdevicename("dpu-1", {}))

    assert json.loads((tmp_path / "evolver-config.json").read_text()) == device
    assert sio.events == [
        {
            "event": "broadcastname",
            "data": device,
            "namespace": "/dpu-evolver",
        },
        {
            "event": "broadcastname",
            "data": device,
            "namespace": "/dpu-evolver",
        },
    ]


def test_dpu_config_and_connection_handlers_emit_current_server_state(
    monkeypatch, tmp_path, capsys
):
    conf, _conf_path = _install_server_state(monkeypatch, tmp_path)
    sio = RecordingSio()
    monkeypatch.setattr(evolver_server, "sio", sio)

    _run(evolver_server.on_connect("dpu-1", {}))
    _run(evolver_server.on_getlastcommands("dpu-1", {}))
    _run(evolver_server.on_disconnect("dpu-1"))

    assert sio.events == [
        {"event": "config", "data": conf, "namespace": "/dpu-evolver"}
    ]
    output = capsys.readouterr().out
    assert "Connected dpu as server" in output
    assert "Disconnected dpu as Server" in output


def test_raw_and_fit_calibration_updates_are_persisted(monkeypatch, tmp_path):
    _install_server_state(monkeypatch, tmp_path)
    calibrations_path = tmp_path / evolver_server.CALIBRATIONS_FILENAME
    calibrations_path.write_text(json.dumps(_calibrations()))
    sio = RecordingSio()
    monkeypatch.setattr(evolver_server, "sio", sio)

    raw_calibration = {
        "name": "od-cal-2026",
        "calibrationType": "od",
        "fits": [],
        "raw": [{"param": "od_90", "vialData": [[1, 2, 3]]}],
    }
    _run(evolver_server.on_setrawcalibration("dpu-1", raw_calibration))
    _run(
        evolver_server.on_setfitcalibrations(
            "dpu-1",
            {
                "name": "od-cal-2026",
                "fit": {
                    "name": "new-od90-fit",
                    "active": False,
                    "params": ["od_90"],
                    "coefficients": [9, 10, 11, 12],
                },
            },
        )
    )

    saved = json.loads(calibrations_path.read_text())
    updated = next(cal for cal in saved if cal["name"] == "od-cal-2026")
    assert updated["raw"] == [{"param": "od_90", "vialData": [[1, 2, 3]]}]
    assert updated["fits"] == [
        {
            "name": "new-od90-fit",
            "active": False,
            "params": ["od_90"],
            "coefficients": [9, 10, 11, 12],
        }
    ]
    assert sio.events == [
        {
            "event": "calibrationrawcallback",
            "data": "success",
            "namespace": "/dpu-evolver",
        }
    ]


def test_attach_uses_virtual_or_mock_serial_without_hardware(monkeypatch, tmp_path):
    conf, _conf_path = _install_server_state(monkeypatch, tmp_path)
    conf.update(
        {
            "serial_port": "/dev/missing-evolver",
            "serial_baudrate": 9600,
            "serial_timeout": 1,
        }
    )
    sio = RecordingSio()
    monkeypatch.setattr(evolver_server, "sio", sio)
    monkeypatch.setattr(evolver_server, "is_virtual_output_enabled", lambda: True)

    evolver_server.attach("virtual-app", conf)

    assert sio.attached_app == "virtual-app"
    assert isinstance(evolver_server.serial_connection, evolver_server.MockSerial)

    sio = RecordingSio()
    monkeypatch.setattr(evolver_server, "sio", sio)
    monkeypatch.setattr(evolver_server, "is_virtual_output_enabled", lambda: False)
    monkeypatch.setenv("EVOLVER_MOCK_SERIAL", "auto")

    def raise_serial_exception(**_kwargs):
        raise evolver_server.serial.serialutil.SerialException("no port")

    monkeypatch.setattr(evolver_server.serial, "Serial", raise_serial_exception)
    evolver_server.attach("mock-app", conf)

    assert sio.attached_app == "mock-app"
    assert isinstance(evolver_server.serial_connection, evolver_server.MockSerial)


def test_serial_communication_rejects_malformed_arduino_responses(
    monkeypatch, tmp_path
):
    conf, _conf_path = _install_server_state(monkeypatch, tmp_path)
    evolver_server.serial_connection = StaticResponseSerial(
        conf, "wrongb,1,2,3,end"
    )

    try:
        evolver_server.serial_communication("od_90", "1000", evolver_server.RECURRING)
    except evolver_server.EvolverSerialError as exc:
        assert "incorrect address" in str(exc)
    else:
        raise AssertionError("expected malformed Arduino address to be rejected")

    evolver_server.serial_connection = StaticResponseSerial(
        conf, "od_90b,1,2,3,bad"
    )
    try:
        evolver_server.serial_communication("od_90", "1000", evolver_server.RECURRING)
    except evolver_server.EvolverSerialError as exc:
        assert "termination string" in str(exc)
    else:
        raise AssertionError("expected malformed Arduino terminator to be rejected")
