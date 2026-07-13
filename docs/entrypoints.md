# Entrypoints

This file lists the runnable entrypoints exposed by the repository. Most
day-to-day commands are Nix flake apps and can be run from the repository root.

## Nix Apps

Run the eVOLVER hardware server:

```bash
nix run .#run-server
```

Run the server with desktop-safe virtual sensor output instead of serial
hardware:

```bash
nix run .#run-virtual-evolver
```

Run the default app. This is the same as `run-server`:

```bash
nix run
nix run .#default
```

Run the local control-plane API. By default it listens on `127.0.0.1:8082`
and forwards validated device commands to `http://127.0.0.1:8081`:

```bash
nix run .#run-control-plane
```

Persist broadcasts from the existing eVOLVER server into raw JSONL data
streams:

```bash
nix run .#run-broadcast-ingest
```

Discover connected serial devices and report their provisioning state:

```bash
nix run .#discover-devices
```

Provision an unprovisioned miniEvolver device. This command prompts before
writing identity data:

```bash
PORT=/dev/ttyACM0 DEVICE_ID=mev-001 OWNER_ID=server-xyz nix run .#provision-device
```

Export calibration data for a provisioned device:

```bash
DEVICE_ID=mev-001 SERVER_ID=server-xyz OUT=device-export.json nix run .#export-calibration
```

Build firmware through the forwarded `evolver-arduino` flake app:

```bash
nix run .#build-firmware
```

Upload firmware through the forwarded `evolver-arduino` flake app:

```bash
PORT=/dev/ttyACM0 nix run .#upload-firmware
```

Run first-time Arduino toolchain setup through the forwarded `evolver-arduino`
flake app:

```bash
nix run .#setup-arduino
```

Run the DPU experiment controller through the sibling DPU checkout's flake app:

```bash
nix run .#run-dpu
```

The wrapper enters `../dpu` and runs `.#run-dpu` by default. Override the checkout location with
`EVOLVER_DPU_DIR=/path/to/dpu` when needed.

The "DPU" is not a fixed machine — it is any computer running the experiment
script. A laptop, lab workstation, or second Pi all work. The script is a
socket.io client that connects to the RPi server; the server does not care what
machine or language is on the other end.

See [DPU_PLAYBOOK.md](DPU_PLAYBOOK.md) for virtual-server and hardware DPU
workflows.

Keep the pinned `evolver-arduino` and `evolver-dpu` flake inputs up to date
when you need changes from those repositories:

```bash
nix flake update evolver-arduino
nix flake update evolver-dpu
```

## Development Shells

Open the integrated workspace shell:

```bash
nix develop
```

Open the Arduino-only shell:

```bash
nix develop .#arduino
```

Open the DPU-only shell:

```bash
nix develop .#dpu
```

## Packages, Checks, And Modules

Build the default package:

```bash
nix build
nix build .#evolver
```

Run all flake checks:

```bash
nix flake check
```

Run hardware-free Python tests directly:

```bash
pytest tests/
```

Available checks:

```bash
nix build .#checks.x86_64-linux.lint
nix build .#checks.x86_64-linux.provisioning-tests
```

The flake also exposes NixOS modules:

```text
nixosModules.default
nixosModules.evolver
```

## Runtime Environment Variables

`EVOLVER_DATA_DIR` controls where the server reads and writes mutable state
such as config and calibration files:

```bash
EVOLVER_DATA_DIR=/var/lib/evolver nix run .#run-server
```

If `EVOLVER_DATA_DIR` is unset, the launcher uses the first available fallback:

```text
$XDG_STATE_HOME/evolver
$HOME/.local/state/evolver
./.evolver-state
```

`EVOLVER_SERIAL_PORT` overrides the configured serial port for the server:

```bash
EVOLVER_SERIAL_PORT=/dev/ttyACM0 nix run .#run-server
```

`EVOLVER_OUTPUT_MODE=virtual` makes broadcasts use the integrated virtual
eVOLVER output provider:

```bash
EVOLVER_OUTPUT_MODE=virtual nix run .#run-server
```

`EVOLVER_MOCK_SERIAL` defaults to `auto` in the Nix launcher. Override it when
you need a specific serial mode:

```bash
EVOLVER_MOCK_SERIAL=0 nix run .#run-server
```

`EVOLVER_CONTROL_HOST` and `EVOLVER_CONTROL_PORT` configure the local
control-plane bind address:

```bash
EVOLVER_CONTROL_PORT=8082 nix run .#run-control-plane
```

`EVOLVER_HARDWARE_URL` points the control plane and broadcast ingester at the
existing eVOLVER Socket.IO server:

```bash
EVOLVER_HARDWARE_URL=http://127.0.0.1:8081 nix run .#run-broadcast-ingest
```

## Legacy Entrypoints

Install with legacy Python packaging:

```bash
python3.6 setup.py install
```

Run the server script directly:

```bash
python3.6 evolver/evolver.py
```

Convert older calibration files:

```bash
python3.6 utils/calibration_transformation.py \
  -d evolver/calibrations \
  -f evolver/calibrations.json
```

Legacy Raspberry Pi deployments may also use:

```text
evolvercron
server_monitor.sh
```
