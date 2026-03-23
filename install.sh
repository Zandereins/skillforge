#!/usr/bin/env bash
##############################################################################
# SkillForge Installer
#
# Installs SkillForge skills and commands to ~/.claude/
# Supports fresh install, update, and --link mode for developers.
#
# Usage:
#   bash install.sh           # copy mode (default)
#   bash install.sh --link    # symlink mode (for developers)
#   bash install.sh --help    # show help
#   bash install.sh --check   # only check prerequisites
##############################################################################

set -euo pipefail

VERSION="5.1.1"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_SRC="$SCRIPT_DIR/skills/skillforge"
COMMANDS_SRC="$SCRIPT_DIR/commands/skillforge"
SKILLS_DST="$HOME/.claude/skills/skillforge"
COMMANDS_DST="$HOME/.claude/commands/skillforge"
LINK_MODE=0
CHECK_ONLY=0

# --- Colors & symbols ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BOLD='\033[1m'
RESET='\033[0m'

ok() { printf "  ${GREEN}✓${RESET} %s\n" "$1"; }
warn() { printf "  ${YELLOW}⚠${RESET} %s\n" "$1"; }
err() { printf "  ${RED}✗${RESET} %s\n" "$1"; }
line() { printf "  ─────────────────────────\n"; }

# --- Usage ---
usage() {
    cat <<EOF
SkillForge v${VERSION} Installer

Usage:
  bash install.sh           Install (copy mode)
  bash install.sh --link    Install (symlink mode, for developers)
  bash install.sh --check   Check prerequisites only
  bash install.sh --help    Show this help

Options:
  --link    Create symlinks instead of copies. Useful when you cloned the
            repo and want changes to propagate via git pull.
  --check   Only verify prerequisites, do not install anything.
  --help    Show this help message.

Paths:
  Skills   → ~/.claude/skills/skillforge/
  Commands → ~/.claude/commands/skillforge/
EOF
    exit 0
}

# --- Parse args ---
for arg in "$@"; do
    case "$arg" in
        --link)  LINK_MODE=1 ;;
        --check) CHECK_ONLY=1 ;;
        --help|-h) usage ;;
        *)
            err "Unknown option: $arg"
            echo "  Run 'bash install.sh --help' for usage."
            exit 1
            ;;
    esac
done

# --- Header ---
echo ""
printf "  ${BOLD}SkillForge v${VERSION} Installer${RESET}\n"
line
echo ""

# --- Prerequisite checks ---
MISSING=0

check_cmd() {
    local cmd="$1"
    local name="$2"
    local min_version="$3"
    local install_hint="$4"

    if ! command -v "$cmd" &>/dev/null; then
        err "$name — not found"
        echo "      Install: $install_hint"
        MISSING=$((MISSING + 1))
        return
    fi

    local ver
    case "$cmd" in
        python3) ver=$(python3 --version 2>&1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1) ;;
        bash)    ver=$(bash --version 2>&1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1) ;;
        git)     ver=$(git --version 2>&1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1) ;;
        jq)      ver=$(jq --version 2>&1 | grep -oE '[0-9]+\.[0-9.]+' | head -1) ;;
    esac

    if [ -z "${ver:-}" ]; then
        warn "$name — installed (version unknown)"
        return
    fi

    ok "$name $ver"
}

check_python_version() {
    if ! command -v python3 &>/dev/null; then
        return
    fi
    local major minor
    major=$(python3 -c "import sys; print(sys.version_info.major)")
    minor=$(python3 -c "import sys; print(sys.version_info.minor)")
    if [ "$major" -lt 3 ] || { [ "$major" -eq 3 ] && [ "$minor" -lt 9 ]; }; then
        err "Python 3.9+ required, found 3.${minor}"
        MISSING=$((MISSING + 1))
    fi
}

check_cmd python3 "Python"  "3.9"   "https://python.org or: brew install python3"
check_python_version
check_cmd bash    "Bash"    "4.0"   "brew install bash"
check_cmd git     "Git"     "2.0"   "https://git-scm.com or: brew install git"
check_cmd jq      "jq"      "1.6"   "https://jqlang.github.io/jq/ or: brew install jq"

echo ""

if [ "$MISSING" -gt 0 ]; then
    err "$MISSING prerequisite(s) missing. Install them and re-run."
    exit 1
fi

if [ "$CHECK_ONLY" -eq 1 ]; then
    ok "All prerequisites satisfied."
    exit 0
fi

# --- Validate source directories ---
if [ ! -d "$SKILLS_SRC" ]; then
    err "Skills source not found: $SKILLS_SRC"
    err "Run this script from the SkillForge repo root."
    exit 1
fi

if [ ! -d "$COMMANDS_SRC" ]; then
    err "Commands source not found: $COMMANDS_SRC"
    err "Run this script from the SkillForge repo root."
    exit 1
fi

# --- Detect install mode ---
if [ -d "$SKILLS_DST" ]; then
    MODE="update"
    printf "  Mode: ${YELLOW}update${RESET} (existing installation detected)\n"
else
    MODE="fresh"
    printf "  Mode: ${GREEN}fresh install${RESET}\n"
fi

if [ "$LINK_MODE" -eq 1 ]; then
    printf "  Strategy: ${YELLOW}symlink${RESET} (developer mode)\n"
else
    printf "  Strategy: copy\n"
fi
echo ""

# --- Backup existing installation on update ---
if [ "$MODE" = "update" ]; then
    BACKUP_DIR="$HOME/.claude/skills/skillforge.bak.$(date +%Y%m%d%H%M%S)"
    cp -r "$SKILLS_DST" "$BACKUP_DIR"
    ok "Backed up existing skills to $BACKUP_DIR"

    if [ -d "$COMMANDS_DST" ]; then
        CMDS_BACKUP="$HOME/.claude/commands/skillforge.bak.$(date +%Y%m%d%H%M%S)"
        cp -r "$COMMANDS_DST" "$CMDS_BACKUP"
        ok "Backed up existing commands to $CMDS_BACKUP"
    fi

    # Clean up old backups, keep most recent 3
    ls -dt "$HOME/.claude/skills/skillforge.bak."* 2>/dev/null | tail -n +4 | xargs rm -rf 2>/dev/null
    ls -dt "$HOME/.claude/commands/skillforge.bak."* 2>/dev/null | tail -n +4 | xargs rm -rf 2>/dev/null
fi

# --- Install ---
install_dir() {
    local src="$1"
    local dst="$2"
    local label="$3"

    # Ensure parent exists
    mkdir -p "$(dirname "$dst")"

    if [ "$LINK_MODE" -eq 1 ]; then
        # Remove existing target (file, dir, or symlink)
        rm -rf "$dst"
        ln -s "$src" "$dst"
        ok "Linked $label → $dst"
    else
        rm -rf "$dst"
        cp -r "$src" "$dst"
        ok "Installed $label to $dst"
    fi
}

echo "  Installing..."
install_dir "$SKILLS_SRC"   "$SKILLS_DST"   "skills"
install_dir "$COMMANDS_SRC" "$COMMANDS_DST"  "commands"

# --- Make scripts executable ---
if [ "$LINK_MODE" -eq 0 ]; then
    find "$SKILLS_DST/scripts" -name "*.sh" -exec chmod +x {} \; 2>/dev/null || true
    find "$SKILLS_DST/scripts" -name "*.py" -exec chmod +x {} \; 2>/dev/null || true
fi

# --- Done ---
echo ""
line
ok "SkillForge v${VERSION} installed successfully!"
echo ""
echo "  Quick start:"
echo "    1. Open Claude Code"
echo "    2. Run /skillforge:doctor to verify installation"
echo "    3. Run /skillforge:init to improve any skill"
echo ""
