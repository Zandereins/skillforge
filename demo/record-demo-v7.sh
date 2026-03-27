#!/bin/bash
# Demo recording script for schliff v7.0.0
# Run from repo root: bash demo/record-demo-v7.sh
set -e
cd "$(dirname "$0")/.."

export FORCE_COLOR=1
export TERM=xterm-256color

CLI="python3 skills/schliff/scripts/cli.py"

# ── Scene 1: Bad skill scored ────────────────────────────────────────
printf '\033[1;36m$ schliff score demo/bad-skill/SKILL.md\033[0m\n\n'
sleep 0.8
$CLI score demo/bad-skill/SKILL.md 2>/dev/null || true
printf '\n'
sleep 3

# ── Scene 2: Good skill (schliff scores itself) ─────────────────────
printf '\033[1;36m$ schliff score skills/schliff/SKILL.md --eval-suite skills/schliff/eval-suite.json\033[0m\n\n'
sleep 0.8
$CLI score skills/schliff/SKILL.md --eval-suite skills/schliff/eval-suite.json 2>/dev/null || true
printf '\n'
sleep 3

# ── Scene 3: Multi-format — score a .cursorrules file ───────────────
printf '\033[1;36m$ schliff score demo/sample-cursorrules/.cursorrules\033[0m\n\n'
sleep 0.8
$CLI score demo/sample-cursorrules/.cursorrules 2>/dev/null || true
printf '\n'
sleep 3

# ── Scene 4: Compare two files side by side ─────────────────────────
printf '\033[1;36m$ schliff compare demo/bad-skill/SKILL.md skills/schliff/SKILL.md\033[0m\n\n'
sleep 0.8
$CLI compare demo/bad-skill/SKILL.md skills/schliff/SKILL.md 2>/dev/null || true
printf '\n'
sleep 3

# ── Scene 5: Suggest ranked fixes ───────────────────────────────────
printf '\033[1;36m$ schliff suggest demo/bad-skill/SKILL.md --top 5\033[0m\n\n'
sleep 0.8
$CLI suggest demo/bad-skill/SKILL.md --top 5 2>/dev/null || true
printf '\n'
sleep 3

# ── Scene 6: Sync check across directory ──────────────────────────────
printf '\033[1;36m$ schliff sync demo/sync-conflict/\033[0m\n\n'
sleep 0.8
$CLI sync demo/sync-conflict/ 2>/dev/null || true
printf '\n'
sleep 3
