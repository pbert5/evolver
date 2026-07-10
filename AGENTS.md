# Agent Instructions

## Required First Steps

1. Read the Serena instructions with `mcp__serena__initial_instructions`.
2. Activate this project with `mcp__serena__activate_project` using the repo root:
   `/home/ash/Documents/work/evolver_code/evolver`.
3. Follow `/home/ash/.codex/RTK.md`: prefix shell commands with `rtk`.

## Python Workflow

Use Serena for Python code navigation and edits.

- Prefer Serena symbol tools for Python files before reading whole source files.
- Use symbol-aware edits for Python symbols when possible.
- Use shell tools for tests, formatting, docs, and non-Python files.
- Do not run hardware tests automatically.

## Validation

- For Python/server changes, run `rtk pytest tests/` when relevant.
- For Nix/package changes, run `rtk nix flake check`; after changes under `nix/`, also run `rtk nix build`.
- Hardware tests require explicit user intent and the `--hardware` flag.
