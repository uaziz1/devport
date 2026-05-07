# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-05-07

### Added
- One-line installer: `curl -fsSL .../install.sh | bash`. Falls back to git install if PyPI release isn't published yet. Seeds an empty registry, idempotent.
- `devport add <project> <name> [port]` — add a port. Auto-allocates in the project's existing 10-block, or claims a fresh block. Prints the port.
- `devport rm <project> [name]` — remove a port, or a whole project block if no name given.
- `devport rename <project> <old> <new>` — rename a port within a project. Port number unchanged.
- `devport init [project]` — wire the current directory to a project in one shot: writes `.envrc` (or appends to an existing one), runs `direnv allow`. Defaults to the cwd basename. Idempotent.
- `devport list` is now project-scoped by default: shows ports for the cwd's inferred project. `devport list all` shows everything. `devport list <project>` is unchanged. Output now includes the env var name each port maps to (e.g., `web  3010  → $WEB_PORT`).
- `devport init` ends with a summary block: shows the registered ports with their env var names, plus drop-in usage examples for `package.json`, `docker-compose.yml`, and `.env`.
- Project inference: when run inside a directory whose `.envrc` was set up by `devport init`, the project name is inferred from the `.envrc`. So `devport add api` (no project) and `devport web` (no project) work from inside the project. Walks up parent directories so you can be in any subfolder.
- Auto-reload: after `devport add`, the relevant `.envrc` is touched so direnv reloads on the next prompt — no manual `direnv reload` or `cd` out and back.
- All write ops are surgical (line-level), so comments, blank lines, and inline `# notes` survive.
- `devport <project> <name>` — resolve a port from the registry.
- `devport list [project]` — show registry contents.
- `devport env <project>` — emit shell `export` lines for direnv / `eval`.
- `devport doctor` — flag registry collisions, currently-bound registered ports, and unregistered listeners in dev port range.
- `devport free` — suggest the next unused 10-port block.
- `devport check <port>` — reverse lookup: who owns this port (registry + live).
- `devport adopt <dir>` — scan a project for hardcoded local ports and report findings.
- TOML registry at `~/.config/dev-ports.toml` (override with `$DEVPORTS_FILE`).
- direnv template + pre-commit hook example.
