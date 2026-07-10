# eVOLVER Server

This repository contains the Python server that runs on an eVOLVER controller
and coordinates communication between the DPU and the microcontrollers that
monitor and actuate experiment parameters. It handles calibration data,
experiment commands, serial device communication, and Socket.IO data exchange.

The repo also provides a Nix flake that packages the server and re-exports
common firmware and DPU workflows from the companion eVOLVER repositories.

## Repository Layout

```text
evolver/                  Python server package
  evolver.py              Server entry point
  evolver_server.py       Socket.IO server and experiment control logic
  provisioning.py         Device identity/provisioning state machine
  serial_discovery.py     Serial port discovery and handshake helpers
  identity_store.py       Device export and calibration I/O
nix/                      Nix package and NixOS module
tests/                    Hardware-free unit tests
utils/                    Maintenance and calibration utilities
flake.nix                 Integrated Nix workspace
```

## Quick Start With Nix

See [entrypoints.md](entrypoints.md) for the full command catalog.

Enter the development shell:

```bash
nix develop
```

Run the server:

```bash
nix run .#run-server
```

Run the server with virtual desktop output instead of hardware serial data:

```bash
nix run .#run-virtual-evolver
```

By default, the Nix launcher stores mutable runtime files in the first
available location:

```text
$EVOLVER_DATA_DIR
$XDG_STATE_HOME/evolver
$HOME/.local/state/evolver
./.evolver-state
```

Set `EVOLVER_DATA_DIR` explicitly when running against a real deployment state
directory:

```bash
EVOLVER_DATA_DIR=/var/lib/evolver nix run .#run-server
```

## Device Discovery And Provisioning

List connected devices and their provisioning state:

```bash
nix run .#discover-devices
```

Provision a new device:

```bash
PORT=/dev/ttyACM0 DEVICE_ID=mev-001 OWNER_ID=server-xyz nix run .#provision-device
```

Export calibration data for a device:

```bash
DEVICE_ID=mev-001 SERVER_ID=server-xyz OUT=device-export.json nix run .#export-calibration
```

Provisioning safety rules:

- Do not bind an `UNKNOWN` or `MISMATCH` device to real calibration data.
- Do not overwrite existing calibration data without an explicit operator
  decision.
- Use automatic provisioning only for CI or simulation workflows, not live
  experiments.

## Legacy Python Installation

Older eVOLVER deployments may install the package directly with Python 3.6:

```bash
python3.6 setup.py install
```

For local development without Nix:

```bash
python3 -m pip install --requirement requirements.txt
python3 -m pip install --requirement test-requirements.txt
```

The historical `README.rst` is still used as the package long description by
`setup.py`.

## Running Tests

Run the hardware-free test suite:

```bash
pytest tests/
```

Run the flake checks:

```bash
nix flake check
```

After changing Nix packaging or modules, also run:

```bash
nix build
```

Hardware tests, if present, are manual-only and should be run only with an
explicit hardware target and the `--hardware` flag.

## Calibration Conversion

To convert older calibration files to the current release format:

```bash
python3.6 utils/calibration_transformation.py \
  -d evolver/calibrations \
  -f evolver/calibrations.json
```

## Deployment Notes

eVOLVER units are typically shipped with the server pre-installed. Legacy
deployments use `supervisor` for process management and include `evolvercron`
and `server_monitor.sh` as monitoring/restart helpers.

The flake also exposes a NixOS module from `nix/evolver-module.nix` for
systemd-based deployments.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for branch and pull request guidance.
