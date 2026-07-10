# Tech Stack

- Python server package with legacy `setup.py`; package metadata still advertises Python 3.5/3.6 and reads dependencies from `requirements.txt` plus `test-requirements.txt`.
- Runtime deps include `aiohttp`, `python-socketio`, `pyserial`, `pyyaml`, `requests`, `six`, `websocket-client`.
- Nix flake is the current integrated workflow; pins `nixpkgs` and sibling flakes `evolver-arduino` and `evolver-dpu`, supports `x86_64-linux` and `aarch64-linux`.
- Nix package patches mutable config/data paths to honor `EVOLVER_DATA_DIR`; default state dir is `$XDG_STATE_HOME/evolver`, `$HOME/.local/state/evolver`, or `./.evolver-state`.
- Supervisor/cron scripts (`evolvercron`, `server_monitor.sh`) are legacy deployment helpers for Raspberry Pi units.