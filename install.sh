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

# --- 2. Sideline any legacy standalone script --------------------------------
LOCAL_BIN="$HOME/.local/bin"
LEGACY="$LOCAL_BIN/devport"
if [[ -f "$LEGACY" && ! -L "$LEGACY" ]]; then
    # A regular file at this path is a hand-written legacy script (the package
    # ships its binary in the Python user-bin dir; we only put a symlink here).
    BAK="$LOCAL_BIN/devport.legacy.bak"
    mv "$LEGACY" "$BAK"
    warn "moved legacy script $LEGACY → $BAK"
fi

# --- 3. Install the CLI -------------------------------------------------------
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

# Probe PyPI directly via HTTP — pip's exit codes lie about already-installed
# packages, so we ask the index ourselves.
pypi_has_devport() {
    [[ "$USE_PYPI" == "1" ]] || return 1
    curl -fsI "https://pypi.org/pypi/${PYPI_TARGET}/json" -o /dev/null 2>/dev/null
}

if pypi_has_devport; then
    SOURCE="PyPI"
    TARGET="$PYPI_TARGET"
else
    SOURCE="git@${REF}"
    TARGET="$GIT_TARGET"
fi

if [[ "$INSTALLER" == "pipx" ]]; then
    pipx install --force "$TARGET" >/dev/null 2>&1 || die "pipx install ($SOURCE) failed"
    INSTALLED_VIA="pipx"
else
    pip3 install --user --quiet --upgrade --force-reinstall \
        --no-warn-script-location --disable-pip-version-check "$TARGET" \
        || die "pip install ($SOURCE) failed"
    INSTALLED_VIA="pip --user"
fi
ok "installed via $INSTALLED_VIA ($SOURCE)"

# --- 4. PATH wiring -----------------------------------------------------------
# pip --user installs the binary into ~/Library/Python/X.Y/bin (or ~/.local/bin
# on Linux). If that's not on PATH, symlink into ~/.local/bin which usually is.
mkdir -p "$LOCAL_BIN"
if ! command -v devport >/dev/null 2>&1; then
    PKG_BIN=""
    for cand in \
        "$HOME/Library/Python/$PY_VER/bin/devport" \
        "$HOME/.local/lib/python$PY_VER/bin/devport" \
        "$(python3 -c 'import sysconfig; print(sysconfig.get_path("scripts", "posix_user"))' 2>/dev/null)/devport" \
    ; do
        if [[ -n "$cand" && -x "$cand" ]]; then
            PKG_BIN="$cand"
            break
        fi
    done
    if [[ -n "$PKG_BIN" ]]; then
        ln -sf "$PKG_BIN" "$LOCAL_BIN/devport"
        ok "linked $LOCAL_BIN/devport → $PKG_BIN"
    fi
fi
hash -r 2>/dev/null || true
if command -v devport >/dev/null 2>&1; then
    ok "devport on \$PATH ($(command -v devport), v$(devport --version))"
else
    warn "devport not on \$PATH yet"
    warn "add this to ~/.bashrc or ~/.zshrc:  export PATH=\"\$HOME/.local/bin:\$PATH\""
fi

# --- 5. Seed registry ---------------------------------------------------------
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

# --- 6. Wrap up ---------------------------------------------------------------
say ""
hdr "Done."
say ""
say "Next:"
say "  Add ports straight from the CLI — no editor needed:"
say ""
say "    devport add my-app web              # → 3010 (auto-allocated)"
say "    devport add my-app api              # → 3011 (next slot in same block)"
say "    devport add my-app worker 4000      # → 4000 (explicit port)"
say ""
say "  Read, audit, change:"
say ""
say "    devport my-app web                  # resolve a port"
say "    devport list                        # show registry"
say "    devport doctor                      # collisions + what's bound"
say "    devport rename my-app web frontend  # rename within a project"
say "    devport rm my-app worker            # remove a port"
say ""
say "  Wire a project to direnv (one shot):"
say ""
say "    cd ~/Dev/<project> && devport init  # writes .envrc + direnv allow"
say ""
say "  Migrate an existing project:"
say ""
say "    devport adopt ~/Dev/<project>       # find hardcoded ports"
say ""
say "Registry: $REGISTRY"
say "Docs:     $REPO_URL"
say ""
say "Optional: install direnv for the cleanest per-project workflow:"
say "  brew install direnv && eval \"\$(direnv hook bash)\" >> ~/.bashrc"
