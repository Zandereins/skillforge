---
name: skillforge:bench
description: >
  Run a full benchmark of a skill's current quality. Measures all 6 dimensions
  (structure, triggers, quality, edges, efficiency, composability) and runs
  binary eval assertions if an eval suite exists. Records results in JSONL format
  and supports comparison against previous benchmarks to show progress deltas.
---

# /skillforge:bench

Establish or update a quality baseline benchmark for the target skill.

## Instructions

1. Identify the target skill path from the user's message.

2. If no eval suite exists and the user hasn't run `/skillforge:init` yet, suggest it:
   ```
   No eval suite found. Run /skillforge:init first to auto-generate one.
   ```

3. Run structural analysis:
   ```bash
   bash scripts/analyze-skill.sh /path/to/SKILL.md
   ```

4. Run the Python scorer to get all 6 dimensions:
   ```bash
   python3 scripts/score-skill.py \
     /path/to/SKILL.md \
     --eval-suite /path/to/skill/eval-suite.json \
     --json
   ```

5. Run binary eval assertions (if eval suite exists):
   ```bash
   bash scripts/run-eval.sh \
     /path/to/SKILL.md \
     --eval-suite /path/to/skill/eval-suite.json \
     --no-runtime-auto
   ```

6. Calculate composite score (weighted average of 6 dimensions) and pass rate:
   - Composite: (structure × 0.15 + triggers × 0.2 + quality × 0.25 + \
     edges × 0.15 + efficiency × 0.15 + composability × 0.1) / 100
   - Pass rate: (assertions_passed / assertions_total)

7. Record the benchmark in skillforge-results.jsonl:
   ```bash
   echo '{"exp": N, "timestamp": "ISO-8601", "trigger": "bench", \
     "composite_score": XX, "pass_rate": "X/Y", "scores": {...}}' \
     >> /path/to/skill/skillforge-results.jsonl
   ```

8. Create a history snapshot of the current SKILL.md:
   ```bash
   cp /path/to/SKILL.md /path/to/skill/skillforge-history/exp-NNN-benchmark.md
   ```

9. If the user provided `--compare FILE`, load the previous benchmark JSON and compute deltas manually:
   - Load both JSON files
   - Calculate per-dimension score differences
   - Calculate composite and pass rate deltas
   - Display with ✓ (improved), ═ (unchanged), ✗ (regressed) markers

10. Present the benchmark report:

    ```
    === SkillForge Benchmark ===
    Skill: [skill-name]

    Composite: XX/100
    Pass Rate: X/Y assertions passing

    Dimension Scores:
    ├─ Structure:     XX   ✓
    ├─ Triggers:      XX   (test accuracy)
    ├─ Quality:       XX   (output correctness)
    ├─ Edges:         XX   (error handling)
    ├─ Efficiency:    XX   (token usage)
    └─ Composability: XX   (scope boundaries)

    Eval Results:
    ├─ Positive triggers: X/5 detected correctly
    ├─ Negative triggers: X/3 rejected correctly
    ├─ Test cases: X/M passing
    └─ Edge cases: X/N handled gracefully

    [If --compare provided]:
    Delta from baseline:
    ├─ Composite: +X points
    ├─ Pass rate: +Y%
    └─ Dimension changes: [...per-dimension deltas...]

    Ready to improve. Run /skillforge to start the loop.
    ```

## Flags

- `--compare FILE`: Compare against a previous benchmark JSON file and show delta.
- `--quick`: Skip full dimension scoring, just run eval assertions (30s instead of 2m).
