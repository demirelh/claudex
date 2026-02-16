#!/usr/bin/env bash
# =============================================================================
# ClaudeX — Global Install Script
# =============================================================================
# Installs ClaudeX globally so it's available from any directory/terminal.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/demirelh/claudex/master/install.sh | bash
#   # or locally:
#   ./install.sh
#
# What it does:
#   1. Checks Python 3.10+
#   2. Installs via pipx (preferred) or pip --user (fallback)
#   3. Verifies 'claudex' is in PATH
# =============================================================================
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
DIM='\033[2m'
BOLD='\033[1m'
RESET='\033[0m'

info()  { echo -e "${BOLD}$*${RESET}"; }
ok()    { echo -e "${GREEN}✓${RESET} $*"; }
err()   { echo -e "${RED}✗${RESET} $*" >&2; }
dim()   { echo -e "${DIM}$*${RESET}"; }

# --- 1. Check Python ---
PYTHON=""
for candidate in python3 python; do
    if command -v "$candidate" &>/dev/null; then
        version=$("$candidate" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || true)
        major=$("$candidate" -c "import sys; print(sys.version_info.major)" 2>/dev/null || echo 0)
        minor=$("$candidate" -c "import sys; print(sys.version_info.minor)" 2>/dev/null || echo 0)
        if [[ "$major" -ge 3 && "$minor" -ge 10 ]]; then
            PYTHON="$candidate"
            break
        fi
    fi
done

if [[ -z "$PYTHON" ]]; then
    err "Python 3.10+ is required but not found."
    echo "  Install it: https://www.python.org/downloads/"
    exit 1
fi

ok "Python $version ($PYTHON)"

# --- 2. Determine install method ---
INSTALL_METHOD=""
REPO_URL="https://github.com/demirelh/claudex.git"
INSTALL_DIR="${CLAUDEX_INSTALL_DIR:-$HOME/.claudex}"

# Check if we're in the repo already
if [[ -f "pyproject.toml" ]] && grep -q 'name = "claudex"' pyproject.toml 2>/dev/null; then
    SOURCE_DIR="$(pwd)"
else
    SOURCE_DIR=""
fi

# Prefer pipx for clean global install
if command -v pipx &>/dev/null; then
    INSTALL_METHOD="pipx"
elif "$PYTHON" -m pipx --version &>/dev/null 2>&1; then
    INSTALL_METHOD="pipx-module"
else
    INSTALL_METHOD="pip-user"
fi

info ""
info "Installing ClaudeX globally via ${INSTALL_METHOD}..."
info ""

# --- 3. Install ---
case "$INSTALL_METHOD" in
    pipx)
        if [[ -n "$SOURCE_DIR" ]]; then
            pipx install --force "$SOURCE_DIR"
        else
            # Clone first, then install
            if [[ -d "$INSTALL_DIR" ]]; then
                dim "Updating existing clone at $INSTALL_DIR"
                git -C "$INSTALL_DIR" pull --quiet 2>/dev/null || true
            else
                dim "Cloning claudex to $INSTALL_DIR"
                git clone --quiet "$REPO_URL" "$INSTALL_DIR"
            fi
            pipx install --force "$INSTALL_DIR"
        fi
        ;;

    pipx-module)
        if [[ -n "$SOURCE_DIR" ]]; then
            "$PYTHON" -m pipx install --force "$SOURCE_DIR"
        else
            if [[ -d "$INSTALL_DIR" ]]; then
                git -C "$INSTALL_DIR" pull --quiet 2>/dev/null || true
            else
                git clone --quiet "$REPO_URL" "$INSTALL_DIR"
            fi
            "$PYTHON" -m pipx install --force "$INSTALL_DIR"
        fi
        ;;

    pip-user)
        if [[ -n "$SOURCE_DIR" ]]; then
            "$PYTHON" -m pip install --user --upgrade --quiet "$SOURCE_DIR"
        else
            if [[ -d "$INSTALL_DIR" ]]; then
                git -C "$INSTALL_DIR" pull --quiet 2>/dev/null || true
            else
                git clone --quiet "$REPO_URL" "$INSTALL_DIR"
            fi
            "$PYTHON" -m pip install --user --upgrade --quiet "$INSTALL_DIR"
        fi

        # Ensure ~/.local/bin is in PATH
        USER_BIN="$HOME/.local/bin"
        if [[ ":$PATH:" != *":$USER_BIN:"* ]]; then
            echo ""
            err "'$USER_BIN' is not in your PATH."
            echo ""
            echo "  Add this to your ~/.bashrc or ~/.zshrc:"
            echo ""
            echo "    export PATH=\"\$HOME/.local/bin:\$PATH\""
            echo ""
            echo "  Then run:  source ~/.bashrc"
            echo ""
        fi
        ;;
esac

# --- 4. Verify ---
echo ""
if command -v claudex &>/dev/null; then
    INSTALLED_PATH="$(command -v claudex)"
    INSTALLED_VERSION="$(claudex --version 2>/dev/null || echo 'unknown')"
    ok "ClaudeX installed successfully!"
    dim "  Binary:  $INSTALLED_PATH"
    dim "  Version: $INSTALLED_VERSION"
    echo ""
    info "Run 'claudex' to start."
else
    # Try hash reset in case shell cache is stale
    hash -r 2>/dev/null || true
    if command -v claudex &>/dev/null; then
        ok "ClaudeX installed successfully!"
        info "Run 'claudex' to start."
    else
        err "Installation completed but 'claudex' is not in PATH."
        echo "  You may need to restart your terminal or add ~/.local/bin to PATH."
    fi
fi
