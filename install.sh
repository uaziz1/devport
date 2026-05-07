#!/usr/bin/env bash
# devport installer
#
#   curl -fsSL https://raw.githubusercontent.com/uaziz1/devport/main/install.sh | bash
#
# Installs the CLI, seeds an empty registry at ~/.config/dev-ports.toml,
# and prints next steps. Idempotent — safe to re-run.
#
# Env overrides:
#   DEVPORTS_FILE     registry path (default: ~/.config/dev-ports.toml)
#   DEVPORT_REF       git ref to install from source (default: main)
#   DEVPORT_PYPI      set to 0 to skip PyPI and install from git
set -euo pipefail

REPO_URL="https://github.com/uaziz1/devport"
REGISTRY="${DEVPORTS_FILE:-$HOME/.config/dev-ports.toml}"
REF="${DEVPORT_REF:-main}"
USE_PYPI="${DEVPORT_PYPI:-1}"

# --- output helpers -----------------------------------------------------------
if [[ -t 1 ]]; then
    BOLD=$'\033[1m' GREEN=$'\033[32m' YELLOW=$'\033[33m' RED=$'\033[31m' RESET=$'\033[0m'
else
    BOLD="" GREEN="" YELLOW="" RED="" RESET=""
fi
say()  { printf "%s\n" "$1"; }
ok()   { printf "  ${GREEN}✓${RESET} %s\n" "$1"; }
warn() { printf "  ${YELLOW}⚠${RESET} %s\n" "$1"; }
die()  { printf "  ${RED}✗${RESET} %s\n" "$1" >&2; exit 1; }
hdr()  { printf "${BOLD}%s${RESET}\n" "$1"; }

hdr "Installing devport"

# --- 1. Python check ----------------------------------------------------------
command -v python3 >/dev/null 2>&1 || die "python3 not found. Install Python 3.11+ first."
PY_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PY_OK=$(python3 -c 'import sys; print(1 if sys.version_info >= (3,11) else 0)')
[[ "$PY_OK" == "1" ]] || die "Python 3.11+ required (you have $PY_VER)."
ok "Python $PY_VER"

# --- 2. Install the CLI -------------------------------------------------------
install_via_pipx() {
    local target="$1"
    pipx install --force "$target" >/dev/null 2>&1
}
install_via_pip() {
    local target="$1"
    pip3 install --user --quiet --upgrade "$target"
}

INSTALLER=""
if command -v pipx >/dev/null 2>&1; then
    INSTALLER="pipx"
elif command -v pip3 >/dev/null 2>&1; then
    INSTALLER="pip"
else
    die "neither pipx nor pip3 found. Install one and re-run."
fi

GIT_TARGET="git+${REPO_URL}.git@${REF}"
PYPI_TARGET="devport"

installed=""
if [[ "$USE_PYPI" == "1" ]]; then
    if [[ "$INSTALLER" == "pipx" ]] && install_via_pipx "$PYPI_TARGET"; then
        installed="pipx (PyPI)"
    elif [[ "$INSTALLER" == "pip" ]] && install_via_pip "$PYPI_TARGET" >/dev/null 2>&1; then
        installed="pip --user (PyPI)"
    fi
fi
if [[ -z "$installed" ]]; then
    if [[ "$INSTALLER" == "pipx" ]]; then
        install_via_pipx "$GIT_TARGET" || die "pipx install from git failed"
        installed="pipx (git@${REF})"
    else
        install_via_pip "$GIT_TARGET" || die "pip install from git failed"
        installed="pip --user (git@${REF})"
    fi
fi
ok "installed via $installed"

# --- 3. PATH check ------------------------------------------------------------
if ! command -v devport >/dev/null 2>&1; then
    BIN="$HOME/.local/bin"
    if [[ -x "$BIN/devport" ]]; then
        warn "$BIN is not on \$PATH"
        warn "add this to ~/.bashrc or ~/.zshrc:"
        printf "      export PATH=\"\$HOME/.local/bin:\$PATH\"\n"
    else
        warn "devport binary not found on \$PATH after install"
        warn "you may need to restart your shell or run: hash -r"
    fi
else
    ok "devport on \$PATH ($(command -v devport))"
fi

# --- 4. Seed registry ---------------------------------------------------------
if [[ -f "$REGISTRY" ]]; then
    ok "registry already exists at $REGISTRY (left untouched)"
else
    mkdir -p "$(dirname "$REGISTRY")"
    cat > "$REGISTRY" <<'EOF'
# devport registry — one block per project.
#
# Convention: 10-port block per project, room for web/api/ws/worker/db.
# Use `devport free` to find the next unused block.
# Use `devport doctor` to audit collisions and currently-bound ports.

# [my-app]
# web = 3010
# api = 3011
EOF
    ok "created $REGISTRY"
fi

# --- 5. Wrap up ---------------------------------------------------------------
say ""
hdr "Done."
say ""
say "Next:"
say "  1. open $REGISTRY and add a project block"
say "  2. devport list                       # confirm it's there"
say "  3. devport adopt ~/Dev/<project>      # find hardcoded ports to migrate"
say ""
say "Optional: install direnv for the cleanest per-project workflow."
say "  brew install direnv && eval \"\$(direnv hook bash)\" >> ~/.bashrc"
say ""
say "Docs: $REPO_URL"
