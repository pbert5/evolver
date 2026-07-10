# Core

- Python eVOLVER hardware server repo; top-level flake orchestrates server plus firmware/DPU sibling flakes.
- Main package: `evolver/`; important entrypoints: `evolver/evolver.py`, `evolver/evolver_server.py`, `evolver/multi_server.py`.
- Device identity/provisioning code: `evolver/provisioning.py`, `evolver/serial_discovery.py`, `evolver/identity_store.py`; tests in `tests/` use fake serial devices and are hardware-free unless under `tests/hardware`.
- Nix packaging/module lives in `nix/`; read `mem:tech_stack` for build/runtime details, `mem:suggested_commands` for runnable commands, `mem:conventions` for repo-specific safety conventions.