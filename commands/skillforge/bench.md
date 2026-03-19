---
name: skillforge:bench
description: >
  Benchmark a skill's current quality as a baseline. Runs the full
  scoring suite and records iteration #0 in the results log. Use
  before starting the improvement loop to establish a starting point.
---

# /skillforge:bench

Establish a quality baseline for the target skill.

## Instructions

1. Identify the target skill path from the user's message.

2. Run structural analysis:
   ```bash
   bash scripts/analyze-skill.sh /path/to/SKILL.md
   ```

3. Run the Python scorer:
   ```bash
   python3 scripts/score-skill.py /path/to/SKILL.md --json
   ```

4. If an eval suite exists (`skillforge-evals.json` in the skill directory),
   include it:
   ```bash
   python3 scripts/score-skill.py /path/to/SKILL.md --eval-suite skillforge-evals.json --json
   ```

5. Initialize the results log from the template:
   ```bash
   cp templates/improvement-log-template.tsv /path/to/skill-dir/skillforge-results.tsv
   ```

6. Record baseline as iteration #0 in the TSV.

7. Present the baseline report:
   ```
   === SkillForge Baseline ===
   Skill: [name]
   Composite: XX/100

   Structure:     XX
   Triggers:      XX
   Quality:       XX (requires eval suite)
   Edges:         XX (requires eval suite)
   Efficiency:    XX
   Composability: XX (requires eval suite)

   Ready to improve. Run /skillforge to start the loop.
   ```
