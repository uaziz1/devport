# devport

*A single source of truth for local dev ports.*

## The problem

When you're working on five projects at the same time, they all want port 3000. Or 4000. Or 9000. Start one, the next one fails to boot. Change a port to unblock yourself, forget you changed it, and now half your configs are out of sync. A week later you've lost count of which app lives where, and `lsof` tells you *something* is bound on 3002 but not *what* or *why*.

It's a mess.

## What devport does

devport gives you a **register** and an **audit**.

- **One file** (`~/.config/dev-ports.toml`) lists which project owns which port. Hand-written, source-controlled in your dotfiles, easy to read.
- **One command** (`devport doctor`) checks the register for collisions, shows you which registered ports are currently bound, and flags squatters: anything listening in your dev-port range that *isn't* in the register.

Your projects stop competing for the same ports. They stop colliding. You stop losing count.

```
$ devport doctor
✓ no registry collisions

● 1 registered port(s) currently bound:
    3001  chief-of-staff.dashboard       ← node(7832)

⚠ unregistered listeners in 3000-3099:
    3000  ← com.docker.backend(91050)
    3002  ← node(35645)
```

That last block is the magic moment: you finally know what `node(35645)` on 3002 actually is. Kill it, register it, or move it. Mess cleaned up.

## How it works (in three sentences)

1. **One file** (`~/.config/dev-ports.toml`) lists which project owns which port.
2. **One CLI** (`devport`) reads that file. `devport my-app web` prints the port.
3. **Each project** replaces hardcoded `3000` with `$WEB_PORT` — via [direnv](docs/direnv.md) or inline `$(devport my-app web)`.

No daemon. No magic. Just a registry and a thin CLI.

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/uaziz1/devport/main/install.sh | bash
```

That's it. The installer:

1. Checks Python 3.11+
2. Installs the `devport` CLI (via `pipx` if you have it, otherwise `pip --user`)
3. Seeds an empty registry at `~/.config/dev-ports.toml`
4. Prints next steps

Idempotent. Safe to re-run. macOS and Linux.

<details>
<summary>Manual install</summary>

```bash
pipx install devport          # or: pip install --user devport
```

Then create the registry yourself:

```bash
mkdir -p ~/.config
touch ~/.config/dev-ports.toml
```

</details>

## Quickstart

```bash
cd ~/Dev/my-app
devport init
```

That's it. `devport init`:

1. Registers the project (uses the cwd basename as the name)
2. Allocates a free port and adds it as `web`
3. Writes `.envrc` with the loader
4. Runs `direnv allow`

In a new shell entering this directory, `$WEB_PORT` is now exported. Replace `3000` literals in your `package.json`, `docker-compose.yml`, etc. with `$WEB_PORT` and you're done.

```bash
echo $WEB_PORT     # → 3010
```

That's the entire happy path. Everything below is for when you need more.

### Adding more ports

```bash
devport add my-app api               # → 3011 (next slot in same block)
devport add my-app worker 4000       # → 4000 (explicit)
```

After adding, run `direnv reload` (or `cd` out and back) and `$API_PORT` / `$WORKER_PORT` are exported.

### Inspecting and changing

```bash
devport list                          # show registry
devport doctor                        # audit collisions + what's bound
devport rename my-app web frontend    # rename within a project
devport rm my-app worker              # remove a port
devport rm my-app                     # remove a whole project
```

### Migrating an existing project

```bash
devport adopt ~/Dev/my-app            # find hardcoded ports
```

All write operations are surgical (line-level), so comments, blank lines, and inline `# notes` in the registry survive.

Requires [direnv](docs/direnv.md) — `init` will tell you if it's missing and how to install it.

## Commands

**Read:**

| Command                       | What it does |
|-------------------------------|--------------|
| `devport <project> <name>`    | Resolve a port. Use in scripts: `$(devport my-app web)` |
| `devport list [project]`      | Show the registry (everything, or one project) |
| `devport env <project>`       | Emit shell `export` lines (use with direnv or `eval`) |
| `devport check <port>`        | Reverse lookup: who owns this port (registry + live)? |
| `devport free`                | Suggest the next unused 10-port block |

**Write** (surgical, comment-preserving):

| Command                                      | What it does |
|----------------------------------------------|--------------|
| `devport add <project> <name> [port]`        | Add a port. Auto-allocates if no port given. Prints the port. |
| `devport rm <project> [name]`                | Remove a port (or the whole project if no name) |
| `devport rename <project> <old> <new>`       | Rename a port within a project |
| `devport init [project]`                     | Wire current dir to a project: write `.envrc` + `direnv allow` |

**Audit:**

| Command                       | What it does |
|-------------------------------|--------------|
| `devport doctor`              | Collisions + currently-bound registered ports + squatters in the dev range |
| `devport adopt <dir>`         | Scan a project for hardcoded local ports |

## The registry

```toml
# ~/.config/dev-ports.toml — one block per project, 10 ports each.

[my-app]
web = 3010
api = 3011

[other-app]
web    = 3020
api    = 3021
worker = 3022

[some-service]
http = 3030
```

Convention: 10-port block per project so you can add services without renumbering. Names are arbitrary (`web`, `api`, `ws`, `worker`, `db`) — `devport env` upper-cases them and adds `_PORT` (so `web` → `WEB_PORT`).

Override the location with `$DEVPORTS_FILE`.

## Enforcement: making sure projects actually use it

The registry only works if it gets used. Three layers, weakest to strongest:

1. **Convention.** Every project's `.envrc` exports the right vars. Easy to forget.
2. **`devport doctor`.** Run it whenever something feels off. Catches drift, doesn't prevent it.
3. **Pre-commit hook.** Fails commits that introduce hardcoded `localhost:3000`. The real teeth. See [docs/pre-commit.md](docs/pre-commit.md).

For onboarding existing projects, see [docs/adopt.md](docs/adopt.md).

## Why not just pick different ports per project?

That's the system you already have. It breaks the moment you `git clone` something or work on a sixth project. The registry is the version of "pick different ports" that survives across machines, projects, and your memory.

## Status

`v0.1.0`. Used daily by the author across ~10 projects on macOS. Linux supported, Windows untested. Patches and reports welcome.

## License

[MIT](LICENSE)
