# Adopting an existing project

The `adopt` command scans a project for hardcoded local ports so you know what to replace.

```bash
devport adopt ~/Dev/my-app
```

Output (example):

```
scanning /Users/me/Dev/my-app

  package.json
    L4   port=3000  "dev": "vite --port 3000"
  docker-compose.yml
    L8   port=4000  - "4000:3000"
  .env
    L1   port=3001  PORT=3001

3 hit(s) across 3 unique port(s): [3000, 3001, 4000]

next steps:
  1. devport add <project> web   # registers a port (auto-allocates)
  2. drop in a .envrc with: eval "$(devport env <project>)"
  3. replace the literals above with $WEB_PORT / $API_PORT / etc.
```

Concretely:

```bash
devport add my-app web      # → 3010
devport add my-app api      # → 3011
devport add my-app worker   # → 3012
```

Then drop in `.envrc`, run `direnv allow`, and replace the literals.

## What it scans

- `package.json`, `docker-compose*.yml`, `Dockerfile`
- `.env`, `.env.*`
- `vite.config.*`, `next.config.*`, `*.config.js`, `*.config.ts`
- `Procfile`, `Makefile`, `fly.toml`, `*.toml`

Skips: `node_modules/`, `.git/`, `dist/`, `build/`, `.next/`, virtualenvs.

## What it doesn't do

`adopt` reports — it doesn't rewrite. The literals still need a human eye to map to the right registry name (is `3000` your `web` or your `api`?). After you've added the block to the registry and dropped in a `.envrc`, do the substitution by hand or with `sed`.

Auto-rewrite is intentionally out of scope: too many config-file dialects to touch with confidence.
