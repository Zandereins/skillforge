---
name: skillforge:auto
description: >
  Run the autonomous self-driving improvement loop. Scores the skill, generates
  improvement gradients, applies deterministic patches, re-scores, and keeps or
  reverts changes automatically. Stops on plateau detection or target reached.
---

# /skillforge:auto

Run the autonomous, script-driven improvement loop on a skill.

## Instructions

1. Identify the target skill path from the user's message. If not provided, ask:
   "Which skill should I auto-improve? Give me the path to its SKILL.md."

2. Verify prerequisites:
   - SKILL.md exists and is readable
   - An eval suite exists (`eval-suite.json` in the skill directory)
   - The skill directory is inside a git repository (required for revert-on-regression)

   If eval suite is missing: "Run `/skillforge:init <path>` first to generate an eval suite."

3. Run the autonomous improvement loop:
   ```bash
   python3 scripts/auto-improve.py /path/to/SKILL.md --json
   ```

4. Monitor output and present progress as it runs:
   ```
   === SkillForge Auto-Improve ===
   Skill: [name]

   Iteration 1: 72 → 75 (+3) ✓ KEEP
   Iteration 2: 75 → 74 (-1) ✗ REVERT
   Iteration 3: 75 → 78 (+3) ✓ KEEP
   ...
   Stopped: Plateau detected (EMA ROI < 0.1)

   Final: 72 → 82 (+10 points in 8 iterations)
   ```

5. After completion, show the summary from the JSON output.

## Flags

- `--max-iterations N`: Maximum number of improvement iterations (default: 30)
- `--dry-run`: Show what would be changed without modifying files
- `--resume`: Resume a previously interrupted auto-improve session

## Stopping Conditions

The loop stops automatically when:
- Composite score reaches 98+
- All dimensions reach 90+
- EMA-based ROI drops below 0.1 for 5 consecutive iterations
- Maximum iterations reached

## Notes

- Each iteration makes ONE atomic change, scores, and keeps or reverts
- All changes are git-committed — full history preserved
- Deterministic patches (frontmatter fixes, TODO cleanup) are applied directly
- Non-deterministic improvements may invoke Claude for generation
- Use `--dry-run` to preview without modifying files
