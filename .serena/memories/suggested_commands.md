# Suggested Commands

- Enter dev shell: `nix develop`
- Run server through flake app: `nix run .#run-server`
- Run server with virtual desktop output: `nix run .#run-virtual-evolver`
- Discover devices: `nix run .#discover-devices`
- Provision device: `PORT=/dev/ttyACM0 DEVICE_ID=mev-001 OWNER_ID=server-xyz nix run .#provision-device`
- Export calibration: `DEVICE_ID=mev-001 SERVER_ID=server-xyz [OUT=device-export.json] nix run .#export-calibration`
- Run hardware-free tests: `pytest tests/`
- Run flake checks: `nix flake check`
- Build package after Nix changes: `nix build`
- Legacy dependency install: `pip install --requirement=requirements.txt --requirement=test-requirements.txt`
- Repo shell instruction from `/home/ash/.codex/RTK.md`: prefix shell commands with `rtk` when using Codex terminal, e.g. `rtk pytest tests/`.