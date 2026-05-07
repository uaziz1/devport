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
SKIP_DIRENV="${DEVPORT_SKIP_DIRENV:-0}"

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

# --- 5. direnv (install + hook) ----------------------------------------------
install_direnv_macos() {
    if ! command -v brew >/dev/null 2>&1; then
        warn "Homebrew not found — install direnv manually: https://direnv.net/docs/installation.html"
        return 1
    fi
    say "  installing direnv via brew (this may take a minute)..."
    if brew install direnv >/dev/null 2>&1; then
        ok "direnv installed via brew"
        return 0
    fi
    warn "brew install direnv failed — install manually"
    return 1
}

ensure_direnv_hook() {
    local shell_name="${SHELL##*/}"
    local rc=""
    case "$shell_name" in
        bash) rc="$HOME/.bashrc" ;;
        zsh)  rc="$HOME/.zshrc" ;;
        *)
            warn "unrecognized shell: $shell_name — add this line to your shell rc:"
            printf "      eval \"\$(direnv hook %s)\"\n" "$shell_name"
            return 1
            ;;
    esac

    local hook_line='eval "$(direnv hook '"$shell_name"')"'

    if [[ -f "$rc" ]] && grep -qF 'direnv hook' "$rc"; then
        ok "direnv hook already in $rc"
        return 0
    fi

    {
        printf "\n# devport / direnv\n"
        printf "%s\n" "$hook_line"
    } >> "$rc"
    ok "added direnv hook to $rc"
    HOOK_ADDED=1
    return 0
}

HOOK_ADDED=0
if [[ "$SKIP_DIRENV" == "1" ]]; then
    warn "skipping direnv setup (DEVPORT_SKIP_DIRENV=1)"
elif command -v direnv >/dev/null 2>&1; then
    ok "direnv already installed"
    ensure_direnv_hook || true
else
    case "$(uname -s)" in
        Darwin)
            install_direnv_macos && ensure_direnv_hook || true
            ;;
        Linux)
            warn "direnv not installed (auto-install on Linux not supported)"
            warn "install with your package manager (e.g. apt install direnv) then re-run"
            warn "  https://direnv.net/docs/installation.html"
            ;;
        *)
            warn "direnv not installed and OS is unsupported for auto-install"
            ;;
    esac
fi

# --- 6. Seed registry --------------------------------------------------------
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

# --- 7. Wrap up --------------------------------------------------------------
say ""
hdr "Done."
say ""
if [[ "$HOOK_ADDED" == "1" ]]; then
    rc=""
    case "${SHELL##*/}" in
        bash) rc="$HOME/.bashrc" ;;
        zsh)  rc="$HOME/.zshrc" ;;
    esac
    say "⚠ Restart your shell (or run: source $rc) to activate the direnv hook."
    say ""
fi
say "Get started in any project — one command:"
say ""
say "    cd ~/Dev/<project> && devport init"
say ""
say "  init registers the project, allocates a port, writes .envrc, and"
say "  runs direnv allow. Then \$WEB_PORT is exported in that directory."
say ""
say "More commands once you need them:"
say ""
say "    devport add api                     # add another port (in cwd)"
say "    devport list                        # show ports for the cwd project"
say "    devport doctor                      # collisions + what's bound"
say "    devport adopt ~/Dev/<project>       # find hardcoded ports to migrate"
say ""
say "Registry: $REGISTRY"
say "Docs:     $REPO_URL"
