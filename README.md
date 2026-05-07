# devport

A single source of truth for local dev ports. Stop the 3000/3001 turf war.

```
$ devport doctor
✓ no registry collisions

● 1 registered port(s) currently bound:
    3001  chief-of-staff.dashboard       ← node(7832)

⚠ unregistered listeners in 3000-3099:
    3000  ← com.docker.backend(91050)
    3002  ← node(35645)
```

If you've ever had three projects fight over `localhost:3000`, this is for you.

## How it works (in three sentences)

1. **One file** (`~/.config/dev-ports.toml`) lists which project owns which port.
2. **One CLI** (`devport`) reads that file. `devport my-app web` prints the port.
3. **Each project** replaces hardcoded `3000` with `$WEB_PORT` — via [direnv](docs/direnv.md) or inline `$(devport my-app web)`.

No daemon. No magic. Just a registry and a thin CLI.

## Install

```bash
pipx install devport
# or
pip install --user devport
```

Requires Python 3.11+. macOS and Linux. Optional: [direnv](https://direnv.net) for the cleanest workflow.

## Quickstart

```bash
# 1. Create the registry
mkdir -p ~/.config
cat > ~/.config/dev-ports.toml <<'EOF'
[my-app]
web = 3010
api = 3011
EOF

# 2. Resolve a port
devport my-app web        # → 3010

# 3. Wire a project (with direnv)
cd ~/Dev/my-app
echo 'eval "$(devport env my-app)"' > .envrc
direnv allow
echo $WEB_PORT            # → 3010
```

Now in `package.json`: `"dev": "vite --port $WEB_PORT"`. Done.

## Commands

| Command                       | What it does |
|-------------------------------|--------------|
| `devport <project> <name>`    | Resolve a port. Use in scripts: `$(devport my-app web)` |
| `devport list [project]`      | Show the registry (everything, or one project) |
| `devport env <project>`       | Emit shell `export` lines (use with direnv or `eval`) |
| `devport check <port>`        | Reverse lookup: who owns this port (registry + live)? |
| `devport free`                | Suggest the next unused 10-port block |
| `devport doctor`              | Audit collisions, currently-bound registered ports, and squatters in the dev range |
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
