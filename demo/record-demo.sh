#!/bin/bash
# Demo recording script for schliff score output
set -e
cd "$(dirname "$0")/.."

# Force color output
export FORCE_COLOR=1
export TERM=xterm-256color

printf '\033[1;36m$ schliff score demo/bad-skill/SKILL.md\033[0m\n\n'
sleep 0.5
python3 skills/schliff/scripts/cli.py score demo/bad-skill/SKILL.md 2>/dev/null || true
printf '\n'
sleep 2

printf '\033[1;36m$ schliff score skills/schliff/SKILL.md\033[0m\n\n'
sleep 0.5
python3 skills/schliff/scripts/cli.py score skills/schliff/SKILL.md --eval-suite skills/schliff/eval-suite.json 2>/dev/null || true
printf '\n'
sleep 2
