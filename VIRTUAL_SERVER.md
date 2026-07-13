# Virtual eVOLVER Server

The virtual eVOLVER server runs the normal eVOLVER Socket.IO server while
replacing hardware serial reads with desktop-safe simulated sensor output. It
is intended for DPU/UI development, demos, and local workflow testing when no
Raspberry Pi or SAMD21 hardware is attached.

Virtual mode is not a separate protocol or standalone emulator. It uses the
same server entry point, config file, Socket.IO namespace, command handling,
calibration handlers, and broadcast event as the hardware server. The only
behavioral change is the output provider used during each broadcast cycle.

The implementation ports the useful behavior from
`FYNCH-BIO/virtual_evolver` branch `computer`: fixed OD and temperature sample
values are broadcast in the current server's normal broadcast schema.

## Run

From the repository root:

```bash
nix run .#run-virtual-evolver
```

This app sets:

```bash
EVOLVER_OUTPUT_MODE=virtual
```

and then starts the same launcher used by:

```bash
nix run .#run-server
```

You can also enable virtual output manually:

```bash
EVOLVER_OUTPUT_MODE=virtual nix run .#run-server
```

The server prints:

```text
Using virtual eVOLVER output; serial connection disabled
```

when virtual mode is active.

## Behavior

Virtual mode keeps the normal server path active:

- The server still listens on the configured Socket.IO port.
- DPU commands still update server config and command queues.
- Broadcast payloads keep the existing shape: `data`, `config`, `ip`, and
  `timestamp`.
- Serial hardware is not opened for output generation.

The simulated broadcast `data` currently includes:

- `od_90`
- `od_135`
- `temp`

The values are deterministic sample readings from the old virtual eVOLVER
desktop branch. They are resized to match each parameter's configured incoming
field count.

The default config expects 16 sleeve values for each broadcasted parameter:

```text
fields_expected_incoming: 17
```

The first incoming field is the serial response marker in hardware mode, so
virtual mode emits `fields_expected_incoming - 1` sensor values. If a parameter
is absent from `experimental_params`, virtual mode does not include it in
`data`.

## How It Works

The runtime loop is the same loop used by the hardware server:

1. `nix run .#run-virtual-evolver` sets `EVOLVER_OUTPUT_MODE=virtual`.
2. The standard server launcher loads `conf.yml`, starts the Socket.IO server,
   and attaches the `/dpu-evolver` namespace.
3. `evolver_server.attach()` detects virtual mode and installs a mock serial
   object instead of opening the configured serial port.
4. On each broadcast tick, the server still processes queued command state and
   clears one-shot command values.
5. Instead of calling hardware serial communication, the broadcast path calls
   `virtual_broadcast_data()`.
6. The server emits the normal `broadcast` event with `data`, `config`, `ip`,
   and `timestamp`.

Commands sent by the DPU or another Socket.IO client still update the runtime
config and are written back to the active `conf.yml`. Immediate commands are
queued and then drained on the next virtual broadcast cycle. Virtual mode does
not model the physical effect of those commands; for example, pump or LED
commands do not change later OD or temperature readings.

## Interacting With It

### Use The DPU

The normal DPU workflow is the preferred way to interact with the virtual
server during application development.

Terminal 1:

```bash
EVOLVER_DATA_DIR=$PWD/.evolver-virtual-state nix run .#run-virtual-evolver
```

Terminal 2:

```bash
nix run .#run-dpu
```

If the DPU checkout is not at `../dpu`, point the wrapper at it:

```bash
EVOLVER_DPU_DIR=/path/to/dpu nix run .#run-dpu
```

See [DPU_PLAYBOOK.md](DPU_PLAYBOOK.md) for the full DPU workflow.

### Connect Directly Over Socket.IO

The server uses namespace:

```text
/dpu-evolver
```

The default port is configured in `evolver/conf.yml`:

```text
8081
```

Useful events:

| Direction | Event | Purpose |
| --- | --- | --- |
| client to server | `getconfig` | Request the active server config. |
| server to client | `config` | Returns the full active config. |
| client to server | `command` | Update a parameter and optionally queue an immediate command. |
| server to client | `commandbroadcast` | Echoes the command payload to connected clients. |
| server to client | `broadcast` | Periodic experiment data and parameter config. |
| client to server | `getcalibrationnames` | Request available calibration names. |
| server to client | `calibrationnames` | Returns calibration name/type pairs. |
| client to server | `getcalibration` | Request one calibration by name. |
| server to client | `calibration` | Returns the matching calibration object. |
| client to server | `getdevicename` | Request the configured device name JSON. |
| client to server | `setdevicename` | Write the configured device name JSON. |
| server to client | `broadcastname` | Returns or broadcasts device name JSON. |

Example Python client:

```python
import socketio

sio = socketio.Client()


@sio.event(namespace="/dpu-evolver")
def connect():
    print("connected")
    sio.emit("getconfig", {}, namespace="/dpu-evolver")


@sio.on("config", namespace="/dpu-evolver")
def on_config(config):
    print("config keys:", sorted(config.keys()))


@sio.on("broadcast", namespace="/dpu-evolver")
def on_broadcast(payload):
    print(payload["timestamp"], payload["data"])


sio.connect("http://127.0.0.1:8081", namespaces=["/dpu-evolver"])
sio.wait()
```

### Send Commands

Send `command` events to the `/dpu-evolver` namespace. A command payload can
include:

| Field | Meaning |
| --- | --- |
| `param` | Parameter name under `experimental_params`, such as `temp`, `stir`, `pump`, `od_led`, `od_90`, or `od_135`. |
| `value` | New parameter value. Lists may use `"NaN"` to leave a sleeve value unchanged. |
| `immediate` | When truthy, queue the command for the next broadcast cycle. |
| `recurring` | Updates whether the parameter participates in recurring command processing. |
| `fields_expected_outgoing` | Updates outgoing field count for the parameter. |
| `fields_expected_incoming` | Updates incoming field count for the parameter. |

Example command:

```python
sio.emit(
    "command",
    {
        "param": "temp",
        "value": ["4095"] * 16,
        "immediate": True,
        "recurring": True,
        "fields_expected_outgoing": 17,
        "fields_expected_incoming": 17,
    },
    namespace="/dpu-evolver",
)
```

The server writes command changes to the active `conf.yml` in
`EVOLVER_DATA_DIR`. Use a disposable data directory for experiments when you do
not want command changes to affect another run.

### Read Broadcasts

Each periodic `broadcast` payload has this shape:

```python
{
    "data": {
        "od_90": ["45294", "..."],
        "od_135": ["404", "..."],
        "temp": ["1949", "..."],
    },
    "config": {
        "od_90": {"recurring": True, "...": "..."},
        "temp": {"recurring": True, "...": "..."},
    },
    "ip": "127.0.0.1",
    "timestamp": 1710000000.0,
}
```

`data` contains virtual sensor readings. `config` contains the active
`experimental_params` state after any command updates. `timestamp` is a Unix
timestamp from the server process.

## Configuration

Runtime state follows the same rules as the normal Nix launcher:

```text
$EVOLVER_DATA_DIR
$XDG_STATE_HOME/evolver
$HOME/.local/state/evolver
./.evolver-state
```

Use an explicit state directory when you want isolated virtual-server state:

```bash
EVOLVER_DATA_DIR=$PWD/.evolver-virtual-state nix run .#run-virtual-evolver
```

The server port comes from `evolver/conf.yml` unless overridden by editing the
runtime config in `EVOLVER_DATA_DIR`.

The default broadcast interval is configured by:

```yaml
broadcast_timing: 20
```

## Testing

Run the focused virtual-output tests:

```bash
nix develop -c pytest tests/test_virtual_output.py -q
```

Run all hardware-free tests:

```bash
nix develop -c pytest tests/ -q
```

Run flake checks:

```bash
nix flake check
```

## Limitations

- Virtual mode is deterministic; it does not yet simulate growth dynamics,
  pump effects, calibration curves, or time-varying sensor drift.
- It simulates server output only. It is not a full hardware protocol emulator.
- It should not be used to validate real calibration or provisioning behavior.
