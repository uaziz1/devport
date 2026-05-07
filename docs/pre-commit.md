# Pre-commit enforcement

The registry only works if it actually gets used. The pre-commit hook is the teeth: it fails the commit if staged changes contain hardcoded local ports (`localhost:3000`, `127.0.0.1:4000`, etc.).

## Option A — vanilla git hook

```bash
cp examples/pre-commit-hook.sh /path/to/project/.git/hooks/pre-commit
chmod +x /path/to/project/.git/hooks/pre-commit
```

Per-clone install. Simple, no dependencies.

## Option B — pre-commit framework

If your project uses [pre-commit](https://pre-commit.com), add to `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/uaziz1/devport
    rev: v0.1.0
    hooks:
      - id: devport-no-hardcoded-ports
```

Then `pre-commit install`.

## Bypassing

When you genuinely need a literal port (e.g. a port that's part of a public spec), bypass with `git commit --no-verify`. Use sparingly — every bypass is a future port collision waiting to happen.
