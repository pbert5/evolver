# DPU Playbook

This playbook covers running the DPU against the eVOLVER server from this
workspace. Use the virtual server path for desktop development and the normal
server path for hardware-connected experiments.

## Fast Path: DPU Against Virtual Server

Terminal 1: start the virtual eVOLVER server.

```bash
EVOLVER_DATA_DIR=$PWD/.evolver-virtual-state nix run .#run-virtual-evolver
```

Terminal 2: start the DPU experiment controller from the sibling DPU checkout's
flake app.

```bash
nix run .#run-dpu
```

The parent flake wrapper expects a sibling DPU checkout at `../dpu`. If your
DPU repo is somewhere else, set `EVOLVER_DPU_DIR`:

```bash
EVOLVER_DPU_DIR=/path/to/dpu nix run .#run-dpu
```

You can also run the DPU app directly from the checkout:

```bash
cd ../dpu
nix run .#run-dpu -- -i 127.0.0.1
```

The parent `evolver` flake keeps a convenience wrapper so server and DPU
workflows can still be launched from one workspace.

Keep the pinned `evolver-dpu` and `evolver-arduino` flake inputs current when
you depend on changes from those repos:

```bash
nix flake update evolver-dpu
nix flake update evolver-arduino
```

Expected behavior:

- The server listens on the configured Socket.IO port, usually `8081`.
- The DPU connects to namespace `/dpu-evolver`.
- Broadcast payloads contain `data`, `config`, `ip`, and `timestamp`.
- Virtual `data` includes deterministic `od_90`, `od_135`, and `temp` readings.

## Hardware Path: DPU Against Real Server

Discover devices first:

```bash
nix run .#discover-devices
```

If needed, provision an unprovisioned device:

```bash
PORT=/dev/ttyACM0 DEVICE_ID=mev-001 OWNER_ID=server-xyz nix run .#provision-device
```

Start the hardware server:

```bash
EVOLVER_DATA_DIR=/var/lib/evolver EVOLVER_SERIAL_PORT=/dev/ttyACM0 nix run .#run-server
```

Start the DPU:

```bash
nix run .#run-dpu
```

Use `EVOLVER_DPU_DIR=/path/to/dpu nix run .#run-dpu` if the DPU checkout is not
at `../dpu`.

## Development Shells

Integrated workspace shell:

```bash
nix develop
```

DPU-only shell forwarded from the DPU flake:

```bash
nix develop .#dpu
```

## Server State

Use separate state directories for virtual and hardware runs so config edits,
calibration files, and device metadata do not leak between workflows.

Virtual state:

```bash
EVOLVER_DATA_DIR=$PWD/.evolver-virtual-state nix run .#run-virtual-evolver
```

Hardware state:

```bash
EVOLVER_DATA_DIR=/var/lib/evolver nix run .#run-server
```

Default state resolution, when `EVOLVER_DATA_DIR` is unset:

```text
$XDG_STATE_HOME/evolver
$HOME/.local/state/evolver
./.evolver-state
```

## Useful Checks

Verify the DPU app is exposed:

```bash
nix flake show --all-systems
```

Check which sibling repo revisions are pinned:

```bash
nix flake metadata
```

Run server-side hardware-free tests:

```bash
nix develop -c pytest tests/ -q
```

Run flake checks:

```bash
nix flake check
```

## Troubleshooting

If the DPU cannot connect:

- Confirm the server is running before starting the DPU.
- Confirm both sides are using the same host and port, usually `8081`.
- Confirm no stale server is already bound to the port.
- Use virtual mode first to separate DPU/network issues from hardware issues.

If virtual broadcasts do not appear:

- Start with `nix run .#run-virtual-evolver`, not `nix run .#run-server`.
- Or set `EVOLVER_OUTPUT_MODE=virtual` explicitly.
- Check server logs for `Using virtual eVOLVER output; serial connection disabled`.

If hardware serial fails:

- Confirm the port exists, for example `/dev/ttyACM0`.
- Confirm the user has permission to open the serial device.
- Confirm `EVOLVER_SERIAL_PORT` matches the discovered port.
- Run `nix run .#discover-devices` before starting the hardware server.

## Safety Rules

- Do not run hardware tests automatically.
- Do not bind `UNKNOWN` or `MISMATCH` devices to real calibration data.
- Do not reuse virtual state as production hardware state.
- Treat virtual output as a DPU/server integration aid, not calibration
  validation.
