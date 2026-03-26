#!/bin/bash
# Demo recording script for schliff v6.3.0
set -e
cd "$(dirname "$0")/.."

export FORCE_COLOR=1
export TERM=xterm-256color

# Scene 1: Bad skill
printf '\033[1;36m$ schliff score demo/bad-skill/SKILL.md\033[0m\n\n'
sleep 0.8
python3 skills/schliff/scripts/cli.py score demo/bad-skill/SKILL.md 2>/dev/null || true
printf '\n'
sleep 3

# Scene 2: Good skill (schliff scores itself)
printf '\033[1;36m$ schliff score skills/schliff/SKILL.md\033[0m\n\n'
sleep 0.8
python3 skills/schliff/scripts/cli.py score skills/schliff/SKILL.md --eval-suite skills/schliff/eval-suite.json 2>/dev/null || true
printf '\n'
sleep 3
