# Claude Working Agreement — evolver

## Required First Steps

1. Call `mcp__plugin_claude-code-home-manager_serena__initial_instructions` and follow the Serena manual.
2. Activate the project: `mcp__plugin_claude-code-home-manager_serena__activate_project` with path `/home/ash/Documents/work/evolver_code`.
3. Read `mem:core` then `mem:evolver/core` for server-specific context. See `mem:nix` for Nix packaging details.

## Serena Tool Usage

Use Serena's semantic tools for all code navigation and editing:
- Prefer `get_symbols_overview` → `find_symbol` over reading whole files.
- Use `replace_symbol_body` for handler edits; `search_for_pattern` when symbol names are uncertain.

## Commits

Commit completed changes after each feature or fix before moving on to the next task.

## Nix Build Check

After any change to `nix/`, verify with `nix build` in this directory before committing.
