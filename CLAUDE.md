# Claude Working Agreement — evolver (workspace root)

## Workspace Layout

```
workspace/
  evolver/          ← this repo: server + top-level flake (orchestration)
  evolver-arduino/  ← firmware flake (github:pbert5/evolver-arduino)
  evolver-dpu/      ← DPU experiment control flake (github:pbert5/dpu)
```

The `evolver/` flake is the parent: it pins the two sibling flakes as inputs
and re-exports their apps and devShells. Changes in a sibling repo must be
committed and pushed there first, then the parent flake lock updated here.

## Required First Steps

1. Call `mcp__serena__initial_instructions` and follow the Serena manual.
2. Activate: `mcp__serena__activate_project` path `/home/ash/Documents/work/evolver`.
3. Use `mcp__mcp-nixos__nix` for any Nix question (packages, options, versions,
   build failures, lock updates). Never guess nixpkgs package availability.

## Serena Tool Usage

Use Serena for all code navigation and editing in Python/Nix files.
`get_symbols_overview` → `find_symbol(include_body=True)` → `replace_symbol_body`
or `replace_content`. Do not use `Edit` on files you haven't read via the Read tool.

## Repository Structure

```
evolver/           Python server package
  evolver.py       entry point
  evolver_server.py socket.io server
  provisioning.py  device state machine
  serial_discovery.py port scanning + handshake
  identity_store.py device export / calibration I/O
nix/
  evolver-package.nix  Nix derivation
  evolver-module.nix   NixOS systemd module
tests/
  fake_serial.py       hardware-free test devices
  test_provisioning.py state machine tests
  test_serial_discovery.py discovery tests
  test_identity_store.py export / import tests
  hardware/            (manual only, never auto-run)
flake.nix              top-level flake (pulls in arduino + dpu)
```

## miniEvolver Identity / Provisioning — Architecture

### Problem being solved
A COM port is not a physical identity. The wrong calibration file applied to
the wrong miniEvolver can corrupt experiments. This system adds persistent
identity so the server always knows which physical device it is talking to.

### Device states (evolver/provisioning.py)
| State | Meaning |
|-------|---------|
| UNKNOWN | No response or unrecognised protocol |
| UNPROVISIONED | Valid miniEvolver firmware, no identity stored |
| KNOWN | Identity matches this server's config |
| MISMATCH | Identity exists but doesn't match expected |

### Provisioning modes
- `ask` (default): require explicit user confirmation
- `button`: require physical hardware action
- `auto`: CI / simulation only — never for real experiments

### Workflow for a new device
1. `nix run .#discover-devices` — find ports, classify devices
2. If UNPROVISIONED: `PORT=... DEVICE_ID=mev-xxx OWNER_ID=server-yyy nix run .#provision-device`
3. Verify with `nix run .#discover-devices` again — device should be KNOWN
4. Export calibration: `DEVICE_ID=mev-xxx SERVER_ID=server-yyy nix run .#export-calibration`

### Calibration safety rules
- Never overwrite existing calibration silently
- Never bind an UNKNOWN or MISMATCH device to real calibration
- Reflashing firmware: treat existing calibration as potentially invalid unless
  firmware/protocol version shows compatibility

## Nix Workflow

### Updating flake inputs after sibling repo changes
```bash
# After pushing changes to evolver-arduino:
nix flake update evolver-arduino

# After pushing changes to evolver-dpu:
nix flake update evolver-dpu

# Commit lock update separately:
git add flake.lock && git commit -m "nix: update evolver-arduino input lock"
```

### Running checks
```bash
nix flake check       # lint + provisioning tests
pytest tests/         # same tests, faster iteration
```

### After any nix/ change
Run `nix build` before committing.

## Commit Guidelines

Format: `<scope>: <what> — <why>`
Scope examples: `server`, `provisioning`, `nix`, `tests`, `docs`

Commit in this order when changes span repos:
1. Commit + push sibling repo (arduino / dpu)
2. `nix flake update <input>` in this repo
3. Commit lock update here
4. Commit any server-side changes that depend on the sibling update

## Test Strategy

- Provisioning tests: `pytest tests/` — no hardware needed
- Hardware tests: `pytest tests/hardware/ --hardware` — manual only, requires real device
- `nix flake check` runs lint + provisioning tests in sandbox

Never run hardware tests automatically. Always require `--hardware` flag and
a visible warning before touching any physical device.
