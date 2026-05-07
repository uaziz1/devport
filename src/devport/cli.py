"""devport CLI — resolve, list, audit, and adopt local dev ports."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

DEFAULT_REGISTRY = Path.home() / ".config" / "dev-ports.toml"
DEV_PORT_RANGE = range(3000, 3100)
BLOCK_SIZE = 10


def registry_path() -> Path:
    return Path(os.environ.get("DEVPORTS_FILE", DEFAULT_REGISTRY))


def load(path: Path | None = None) -> dict[str, dict[str, int]]:
    p = path or registry_path()
    if not p.exists():
        sys.exit(f"devport: registry not found at {p}")
    with p.open("rb") as f:
        return tomllib.load(f)


def lsof_path() -> str | None:
    return shutil.which("lsof") or ("/usr/sbin/lsof" if Path("/usr/sbin/lsof").exists() else None)


def listening_ports() -> dict[int, str]:
    """Return {port: 'command(pid)'} for currently-bound TCP listeners."""
    lsof = lsof_path()
    if not lsof:
        return {}
    try:
        out = subprocess.run(
            [lsof, "-iTCP", "-sTCP:LISTEN", "-nP", "-F", "pcPn"],
            capture_output=True, text=True, timeout=5,
        ).stdout
    except (subprocess.SubprocessError, OSError):
        return {}
    bound: dict[int, str] = {}
    pid = cmd = ""
    for line in out.splitlines():
        if not line:
            continue
        tag, val = line[0], line[1:]
        if tag == "p":
            pid = val
        elif tag == "c":
            cmd = val
        elif tag == "n" and ":" in val:
            try:
                port = int(val.rsplit(":", 1)[1])
            except ValueError:
                continue
            bound.setdefault(port, f"{cmd}({pid})")
    return bound


def cmd_get(project: str, name: str) -> None:
    data = load()
    if project not in data:
        sys.exit(f"devport: no project '{project}' in registry")
    ports = data[project]
    if name not in ports:
        sys.exit(f"devport: no port '{name}' for '{project}' (have: {', '.join(ports)})")
    print(ports[name])


def cmd_list(project: str | None) -> None:
    data = load()
    targets = [project] if project else list(data.keys())
    for p in targets:
        if p not in data:
            sys.exit(f"devport: no project '{p}'")
        print(f"\n[{p}]")
        for name, port in data[p].items():
            print(f"  {name:<12} {port}")


def cmd_env(project: str) -> None:
    data = load()
    if project not in data:
        sys.exit(f"devport: no project '{project}'")
    for name, port in data[project].items():
        var = name.upper().replace("-", "_") + "_PORT"
        print(f"export {var}={port}")


def cmd_check(port_str: str) -> None:
    try:
        port = int(port_str)
    except ValueError:
        sys.exit(f"devport: '{port_str}' is not a port number")
    data = load()
    owners = [
        f"{project}.{name}"
        for project, ports in data.items()
        for name, p in ports.items()
        if p == port
    ]
    if owners:
        print(f"registry: {', '.join(owners)}")
    else:
        print("registry: (unallocated)")
    bound = listening_ports().get(port)
    print(f"live:     {bound or '(not bound)'}")


def cmd_free() -> None:
    data = load()
    used = {p for ports in data.values() for p in ports.values()}
    for start in range(DEV_PORT_RANGE.start, DEV_PORT_RANGE.stop, BLOCK_SIZE):
        block = set(range(start, start + BLOCK_SIZE))
        if not block & used:
            print(f"{start}-{start + BLOCK_SIZE - 1}")
            return
    sys.exit("devport: no free 10-port block in 3000-3099")


def cmd_doctor() -> int:
    data = load()
    issues = 0

    seen: dict[int, list[str]] = {}
    for project, ports in data.items():
        for name, port in ports.items():
            seen.setdefault(port, []).append(f"{project}.{name}")
    collisions = {p: refs for p, refs in seen.items() if len(refs) > 1}
    if collisions:
        issues += len(collisions)
        print("✗ registry collisions:")
        for port, refs in sorted(collisions.items()):
            print(f"    {port}: {', '.join(refs)}")
    else:
        print("✓ no registry collisions")

    bound = listening_ports()
    if bound:
        live = [(port, refs[0], bound[port]) for port, refs in seen.items() if port in bound]
        if live:
            print(f"\n● {len(live)} registered port(s) currently bound:")
            for port, ref, who in sorted(live):
                print(f"    {port}  {ref:<30} ← {who}")
        else:
            print("\n✓ no registered ports currently bound")
        registered = set(seen.keys())
        squatters = [
            (p, who) for p, who in bound.items()
            if p in DEV_PORT_RANGE and p not in registered
        ]
        if squatters:
            print("\n⚠ unregistered listeners in 3000-3099:")
            for port, who in sorted(squatters):
                print(f"    {port}  ← {who}")
    else:
        print("\n● lsof unavailable — skipped live-binding check")

    return 1 if issues else 0


# Adopt: scan a project for hardcoded ports.
ADOPT_PATTERNS = [
    # localhost:3000, 127.0.0.1:3000, http://...:3000
    re.compile(r"(?:localhost|127\.0\.0\.1|0\.0\.0\.0):(\d{4,5})"),
    # YAML/env: port: 3000, PORT=3000, --port 3000, --port=3000
    re.compile(r"(?:^|\b)(?:port|PORT)\s*[:=]\s*(\d{4,5})\b", re.IGNORECASE),
    re.compile(r"--port[ =](\d{4,5})\b"),
]
ADOPT_GLOBS = [
    "package.json", "docker-compose*.yml", "docker-compose*.yaml",
    "Dockerfile", ".env", ".env.*", "vite.config.*", "next.config.*",
    "*.toml", "Procfile", "Makefile", "fly.toml", "*.config.js",
    "*.config.ts",
]
ADOPT_SKIP_DIRS = {"node_modules", ".git", "dist", "build", ".next", ".venv", "venv", "__pycache__"}


def _scan_file(path: Path) -> list[tuple[int, int, str]]:
    """Return [(line_no, port, line_text)] for ports found."""
    hits: list[tuple[int, int, str]] = []
    try:
        text = path.read_text(errors="replace")
    except OSError:
        return hits
    for lineno, line in enumerate(text.splitlines(), 1):
        for pat in ADOPT_PATTERNS:
            for m in pat.finditer(line):
                try:
                    port = int(m.group(1))
                except ValueError:
                    continue
                if 1024 <= port <= 65535:
                    hits.append((lineno, port, line.strip()))
    return hits


def cmd_adopt(target: str) -> None:
    root = Path(target).expanduser().resolve()
    if not root.is_dir():
        sys.exit(f"devport: not a directory: {root}")
    print(f"scanning {root}\n")

    candidates: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in ADOPT_SKIP_DIRS for part in path.relative_to(root).parts):
            continue
        if any(path.match(g) for g in ADOPT_GLOBS):
            candidates.append(path)

    if not candidates:
        print("no matching config files found")
        return

    total = 0
    found_ports: set[int] = set()
    for path in sorted(candidates):
        hits = _scan_file(path)
        if not hits:
            continue
        rel = path.relative_to(root)
        print(f"  {rel}")
        for lineno, port, snippet in hits:
            print(f"    L{lineno}  port={port}  {snippet[:80]}")
            found_ports.add(port)
            total += 1

    if total == 0:
        print("no hardcoded ports detected")
        return

    print(f"\n{total} hit(s) across {len(found_ports)} unique port(s): {sorted(found_ports)}")
    print("\nnext steps:")
    print("  1. add a block to ~/.config/dev-ports.toml (try: devport free)")
    print("  2. drop in a .envrc with: eval \"$(devport env <project>)\"")
    print("  3. replace the literals above with $WEB_PORT / $API_PORT / etc.")


USAGE = """\
usage: devport <command> [args]

  devport <project> <name>      resolve a port (e.g. devport cadrano web)
  devport list [project]        show registry
  devport env <project>         emit shell exports (use with direnv or `eval $(...)`)
  devport check <port>          reverse lookup: who owns this port
  devport free                  suggest next unused 10-port block
  devport doctor                audit collisions + currently-bound ports
  devport adopt <dir>           scan a project for hardcoded ports
  devport --version             print version

registry: ~/.config/dev-ports.toml (override with $DEVPORTS_FILE)
"""


def main(argv: list[str] | None = None) -> None:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ("-h", "--help", "help"):
        print(USAGE)
        return
    if args[0] in ("-V", "--version"):
        from devport import __version__
        print(__version__)
        return

    cmd = args[0]
    if cmd == "list":
        cmd_list(args[1] if len(args) > 1 else None)
    elif cmd == "env":
        if len(args) != 2:
            sys.exit("usage: devport env <project>")
        cmd_env(args[1])
    elif cmd == "check":
        if len(args) != 2:
            sys.exit("usage: devport check <port>")
        cmd_check(args[1])
    elif cmd == "free":
        cmd_free()
    elif cmd == "doctor":
        sys.exit(cmd_doctor())
    elif cmd == "adopt":
        if len(args) != 2:
            sys.exit("usage: devport adopt <dir>")
        cmd_adopt(args[1])
    elif len(args) == 2:
        cmd_get(args[0], args[1])
    else:
        print(USAGE, file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
