---
name: skillforge:doctor
description: >
  Run a health check on all installed skills. Scans skill directories, scores
  each skill structurally, and produces a summary table with grades and
  actionable recommendations. Zero arguments needed.
---

# /skillforge:doctor

Run a comprehensive health check on all installed skills.

## Instructions

1. Run the doctor script:
   ```bash
   python3 scripts/doctor.py --json
   ```

2. Parse the JSON output and present results as a readable table:

   ```
   === SkillForge Doctor ===

   Scanning installed skills...

   | Skill | Score | Grade | Issues | Action |
   |-------|-------|-------|--------|--------|
   | my-skill | 85 | A | 0 critical | Healthy |
   | debug | 62 | C | 2 warnings | Run /skillforge:analyze |
   | deploy | 45 | D | 3 critical | Needs improvement |

   Summary: X skills scanned, Y healthy, Z need attention
   ```

3. For skills with grade D or F, suggest specific next steps:
   - "Run `/skillforge:init <path>` to set up improvement tracking"
   - "Run `/skillforge:analyze <path>` for detailed gap analysis"

4. If `--verbose` flag is provided, show per-dimension breakdowns for each skill.

## Flags

- `--verbose`: Show per-dimension scores for each skill
- `--skill-dirs DIR...`: Override default scan directories

## Notes

- Default scan directories: `~/.claude/skills/` and `.claude/skills/`
- Uses structural scoring only (no runtime eval needed)
- Quick to run — takes ~5-10 seconds for most installations
