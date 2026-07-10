# Conventions

- Use Serena for Python code navigation and edits; prefer symbol tools before reading whole Python source files.
- Never run hardware tests automatically; only run `pytest tests/hardware/ --hardware` when explicitly requested and real hardware is intended.
- Provisioning modes: `ask` is default for real devices, `button` requires physical action, `auto` is for CI/simulation only.
- Device identity safety: do not bind UNKNOWN or MISMATCH devices to real calibration; do not silently overwrite calibration data.
- Flake spans sibling repos: commit/push sibling repo changes first, then update this repo's flake input lock.
- Commit format convention in repo notes: `<scope>: <what> — <why>`.