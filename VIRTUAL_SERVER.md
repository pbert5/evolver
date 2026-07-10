# Virtual eVOLVER Server

The virtual eVOLVER server runs the normal eVOLVER Socket.IO server with
desktop-safe simulated sensor output instead of hardware serial output. It is
intended for DPU/UI development, demos, and local workflow testing when no
Raspberry Pi or SAMD21 hardware is attached.

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
