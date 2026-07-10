# Task Completion

- For Python/server changes: run `pytest tests/` when relevant.
- For Nix/package/module changes: run `nix flake check`; also run `nix build` after any `nix/` change.
- Do not run `tests/hardware` automatically; require explicit hardware intent and `--hardware`.
- For docs-only README changes, no test command is required unless examples or commands were changed enough to need verification.
- User can sanity-check memory references with `serena memories check` from the project root.