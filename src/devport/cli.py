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


# --- envrc inference + direnv auto-reload ------------------------------------

ENVRC_PROJECT_RE = re.compile(r"devport env ([a-zA-Z0-9._-]+)")


def _walk_up_for_envrc():
    """Yield .envrc paths walking from cwd up to home/filesystem root."""
    home = Path.home()
    path = Path.cwd()
    visited: set[Path] = set()
    while path not in visited:
        visited.add(path)
        envrc = path / ".envrc"
        if envrc.is_file():
            yield envrc
        if path == home or path.parent == path:
            break
        path = path.parent


def _find_envrc_for_project(project: str | None = None) -> tuple[Path, str] | None:
    """Return (envrc_path, project_name) for the first .envrc that wires devport,
    optionally matching `project`. None if not found."""
    for envrc in _walk_up_for_envrc():
        try:
            text = envrc.read_text()
        except OSError:
            continue
        m = ENVRC_PROJECT_RE.search(text)
        if not m:
            continue
        name = m.group(1)
        if project is None or name == project:
            return (envrc, name)
    return None


def _infer_project() -> str | None:
    found = _find_envrc_for_project()
    return found[1] if found else None


def _trigger_direnv_reload(project: str) -> bool:
    """Touch the .envrc that wires this project so direnv reloads on next prompt.
    Returns True if a relevant .envrc was touched."""
    if not shutil.which("direnv"):
        return False
    found = _find_envrc_for_project(project)
    if not found:
        return False
    try:
        found[0].touch()
        return True
    except OSError:
        return False


# --- file mutation helpers (line-level, comment-preserving) -------------------

def _read_lines(path: Path) -> list[str]:
    return path.read_text().splitlines(keepends=True) if path.exists() else []


def _write_lines(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(lines))


def _project_range(lines: list[str], project: str) -> tuple[int, int] | None:
    """Return [header_idx, end_exclusive) line range for a project block, or None."""
    header = f"[{project}]"
    start = -1
    for i, line in enumerate(lines):
        s = line.strip()
        if s == header:
            start = i
        elif start >= 0 and s.startswith("[") and s.endswith("]"):
            return (start, i)
    if start >= 0:
        return (start, len(lines))
    return None


def _find_port_line(lines: list[str], project: str, name: str) -> int | None:
    rng = _project_range(lines, project)
    if not rng:
        return None
    pat = re.compile(rf"^\s*{re.escape(name)}\s*=")
    for i in range(rng[0] + 1, rng[1]):
        if pat.match(lines[i]):
            return i
    return None


def _allocate_port(data: dict[str, dict[str, int]], project: str) -> int:
    """Pick the next free port: in-block if project exists, else new 10-block."""
    used = {p for ports in data.values() for p in ports.values()}
    if project in data and data[project]:
        block_start = (min(data[project].values()) // BLOCK_SIZE) * BLOCK_SIZE
        for cand in range(block_start, block_start + BLOCK_SIZE):
            if cand not in used:
                return cand
        sys.exit(
            f"devport: '{project}' block {block_start}-{block_start + BLOCK_SIZE - 1} is full; "
            "specify a port explicitly"
        )
    for start in range(DEV_PORT_RANGE.start, DEV_PORT_RANGE.stop, BLOCK_SIZE):
        if not set(range(start, start + BLOCK_SIZE)) & used:
            return start
    sys.exit("devport: no free 10-port block in 3000-3099")


def _add_port(project: str, name: str, port: int | None = None) -> int:
    """Add a port to the registry. Returns the resulting port. Exits on conflict."""
    data: dict[str, dict[str, int]] = {}
    path = registry_path()
    if path.exists():
        with path.open("rb") as f:
            data = tomllib.load(f)

    if project in data and name in data[project]:
        sys.exit(f"devport: {project}.{name} already exists ({data[project][name]})")

    if port is None:
        port = _allocate_port(data, project)
    else:
        for proj, ports in data.items():
            for n, p in ports.items():
                if p == port:
                    sys.exit(f"devport: port {port} already in use by {proj}.{n}")

    lines = _read_lines(path)
    rng = _project_range(lines, project)
    new_line = f"{name} = {port}\n"
    if rng:
        insert_at = rng[1]
        while insert_at > rng[0] + 1 and lines[insert_at - 1].strip() == "":
            insert_at -= 1
        lines.insert(insert_at, new_line)
    else:
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
        if lines and lines[-1].strip() != "":
            lines.append("\n")
        lines.append(f"[{project}]\n")
        lines.append(new_line)
    _write_lines(path, lines)
    return port


def cmd_add(project: str | None, name: str, port_str: str | None) -> None:
    if project is None:
        project = _infer_project()
        if project is None:
            sys.exit(
                "devport: no project inferred from .envrc; "
                "use: devport add <project> <name> [port]"
            )
    port: int | None = None
    if port_str is not None:
        try:
            port = int(port_str)
        except ValueError:
            sys.exit(f"devport: '{port_str}' is not a port number")
    p = _add_port(project, name, port)
    print(p)
    if _trigger_direnv_reload(project):
        print("  ↻ direnv will reload on next prompt", file=sys.stderr)


def cmd_rm(project: str, name: str | None) -> None:
    path = registry_path()
    lines = _read_lines(path)
    rng = _project_range(lines, project)
    if not rng:
        sys.exit(f"devport: no project '{project}'")

    if name is None:
        end = rng[1]
        if end < len(lines) and lines[end].strip() == "":
            end += 1
        del lines[rng[0]:end]
        _write_lines(path, lines)
        print(f"removed project: {project}")
        return

    idx = _find_port_line(lines, project, name)
    if idx is None:
        sys.exit(f"devport: no port '{name}' in project '{project}'")
    del lines[idx]
    _write_lines(path, lines)
    print(f"removed: {project}.{name}")


def cmd_rename(project: str, old: str, new: str) -> None:
    data = load()
    if project not in data:
        sys.exit(f"devport: no project '{project}'")
    if old not in data[project]:
        sys.exit(f"devport: no port '{old}' in project '{project}'")
    if new == old:
        sys.exit("devport: old and new names are the same")
    if new in data[project]:
        sys.exit(f"devport: '{new}' already exists in project '{project}'")

    path = registry_path()
    lines = _read_lines(path)
    idx = _find_port_line(lines, project, old)
    if idx is None:
        sys.exit("devport: internal error locating port line")
    lines[idx] = re.sub(
        rf"^(\s*){re.escape(old)}(\s*=)", rf"\g<1>{new}\g<2>", lines[idx]
    )
    _write_lines(path, lines)
    print(f"renamed: {project}.{old} -> {project}.{new}")


def cmd_init(project: str | None) -> None:
    """One-shot per-project setup: register the project, write .envrc, direnv allow."""
    cwd = Path.cwd()
    proj = project or cwd.name
    if not re.match(r"^[a-zA-Z0-9._-]+$", proj):
        sys.exit(
            f"devport: '{proj}' is not a valid project name; "
            "pass one explicitly: devport init <project>"
        )

    path = registry_path()
    data: dict[str, dict[str, int]] = {}
    if path.exists():
        with path.open("rb") as f:
            data = tomllib.load(f)

    # New (or empty) project? Seed it with a 'web' port so the .envrc has something to export.
    if proj not in data or not data[proj]:
        port = _add_port(proj, "web")
        print(f"  ✓ added {proj}.web = {port}")
    else:
        existing = ", ".join(f"{n}={p}" for n, p in data[proj].items())
        print(f"  ✓ project '{proj}' already in registry ({existing})")

    envrc = cwd / ".envrc"
    line = f'eval "$(devport env {proj})"'
    if envrc.exists():
        text = envrc.read_text()
        if line in text:
            print(f"  .envrc already wired for '{proj}' (no change)")
        else:
            envrc.write_text(text.rstrip("\n") + "\n" + line + "\n")
            print(f"  appended devport line to {envrc}")
    else:
        envrc.write_text(line + "\n")
        print(f"  wrote {envrc}")

    if shutil.which("direnv"):
        try:
            subprocess.run(["direnv", "allow", str(cwd)], check=False, capture_output=True)
            print("  direnv allow ✓")
        except OSError:
            print("  direnv allow failed — run it manually")
    else:
        print("  ⚠ direnv not installed — .envrc won't auto-load")
        print("    install: brew install direnv")
        print("    then add to your shell rc: eval \"$(direnv hook bash)\"")


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
    print("  1. devport add <project> web   # registers a port (auto-allocates)")
    print("  2. drop in a .envrc with: eval \"$(devport env <project>)\"")
    print("  3. replace the literals above with $WEB_PORT / $API_PORT / etc.")


USAGE = """\
usage: devport <command> [args]

When you're inside a project directory (where `.envrc` was set up by
`devport init`), the project name is inferred — drop the first argument:

  devport web                       resolve `web` in the inferred project
  devport add api                   add `api` to the inferred project
  devport add api 5000              ...with an explicit port

read:
  devport <project> <name>          resolve a port (e.g. devport my-app web)
  devport list [project]            show registry
  devport env <project>             emit shell exports (use with direnv or `eval`)
  devport check <port>              reverse lookup: who owns this port
  devport free                      suggest next unused 10-port block

write:
  devport add [<project>] <name> [port]  add a port (auto-allocates if no port)
  devport rm <project> [name]            remove a port (or whole project if no name)
  devport rename <project> <old> <new>   rename a port within a project
  devport init [project]                 wire current dir (.envrc + direnv allow)

audit:
  devport doctor                    collisions + currently-bound ports
  devport adopt <dir>               scan a project for hardcoded ports

  devport --version                 print version

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
    elif cmd == "add":
        rest = args[1:]
        if len(rest) == 1:
            cmd_add(None, rest[0], None)
        elif len(rest) == 2:
            # `add <name> <port>` (inferred project) if 2nd is digits, else
            # `add <project> <name>` (auto-port).
            if rest[1].isdigit():
                cmd_add(None, rest[0], rest[1])
            else:
                cmd_add(rest[0], rest[1], None)
        elif len(rest) == 3:
            cmd_add(rest[0], rest[1], rest[2])
        else:
            sys.exit("usage: devport add [<project>] <name> [port]")
    elif cmd == "rm":
        if len(args) not in (2, 3):
            sys.exit("usage: devport rm <project> [name]")
        cmd_rm(args[1], args[2] if len(args) == 3 else None)
    elif cmd == "rename":
        if len(args) != 4:
            sys.exit("usage: devport rename <project> <old> <new>")
        cmd_rename(args[1], args[2], args[3])
    elif cmd == "init":
        if len(args) > 2:
            sys.exit("usage: devport init [project]")
        cmd_init(args[1] if len(args) == 2 else None)
    elif len(args) == 2:
        cmd_get(args[0], args[1])
    elif len(args) == 1:
        # Bare `devport <name>` — try to resolve in the inferred project.
        project = _infer_project()
        if project is None:
            print(USAGE, file=sys.stderr)
            sys.exit(2)
        cmd_get(project, args[0])
    else:
        print(USAGE, file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
