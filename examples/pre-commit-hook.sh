#!/usr/bin/env bash
# devport pre-commit hook — fails the commit if staged changes introduce
# hardcoded local ports outside the registry.
#
# Install:
#   cp examples/pre-commit-hook.sh .git/hooks/pre-commit
#   chmod +x .git/hooks/pre-commit
#
# Or use with the `pre-commit` framework via examples/pre-commit-hooks.yaml.

set -euo pipefail

PATTERN='(localhost|127\.0\.0\.1):(3[0-9]{3}|4[0-9]{3}|5[0-9]{3}|8[0-9]{3})'
STAGED=$(git diff --cached --name-only --diff-filter=ACM | grep -Ev '\.lock$|node_modules/|\.min\.' || true)

[[ -z "$STAGED" ]] && exit 0

OFFENDERS=$(echo "$STAGED" | xargs grep -EHn "$PATTERN" 2>/dev/null || true)

if [[ -n "$OFFENDERS" ]]; then
    echo "✗ devport: hardcoded local ports detected in staged changes:" >&2
    echo "" >&2
    echo "$OFFENDERS" >&2
    echo "" >&2
    echo "Use the registry: \$(devport <project> <name>) or \$WEB_PORT via direnv." >&2
    echo "Override (not recommended): git commit --no-verify" >&2
    exit 1
fi

exit 0
