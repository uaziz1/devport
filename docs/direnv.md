# Using devport with direnv

[direnv](https://direnv.net) is the cleanest way to wire devport into a project. Every shell that `cd`s into the project gets `WEB_PORT`, `API_PORT`, etc. exported automatically.

## One-time setup

```bash
brew install direnv
# bash:
echo 'eval "$(direnv hook bash)"' >> ~/.bashrc
# zsh:
echo 'eval "$(direnv hook zsh)"' >> ~/.zshrc
```

## Per project

```bash
cd ~/Dev/my-app

cat > .envrc <<'EOF'
eval "$(devport env my-app)"
EOF

direnv allow
```

That's it. Now `echo $WEB_PORT` returns the registered port whenever you're in that directory.

## Wiring it into the code

Replace literals with the env vars:

**`package.json`:**
```json
{ "scripts": { "dev": "vite --port $WEB_PORT" } }
```

**`docker-compose.yml`:**
```yaml
services:
  web:
    ports:
      - "${WEB_PORT}:3000"   # left side = host (registry); right side = container (fixed)
```

**`.env`:** delete duplicates — direnv already exports them.

**Vite (`vite.config.ts`):**
```ts
export default { server: { port: Number(process.env.WEB_PORT) || 3000 } }
```

## Adding services to a project

When the project gains a new service, add a name to its block in `~/.config/dev-ports.toml`:

```toml
[my-app]
web    = 3010
api    = 3011
worker = 3012   # new
```

Run `direnv reload` (or just `cd` in/out). `WORKER_PORT` is now exported.
