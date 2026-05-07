# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-05-07

### Added
- `devport <project> <name>` — resolve a port from the registry.
- `devport list [project]` — show registry contents.
- `devport env <project>` — emit shell `export` lines for direnv / `eval`.
- `devport doctor` — flag registry collisions, currently-bound registered ports, and unregistered listeners in dev port range.
- `devport free` — suggest the next unused 10-port block.
- `devport check <port>` — reverse lookup: who owns this port (registry + live).
- `devport adopt <dir>` — scan a project for hardcoded local ports and report findings.
- TOML registry at `~/.config/dev-ports.toml` (override with `$DEVPORTS_FILE`).
- direnv template + pre-commit hook example.
