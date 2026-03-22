---
name: skillforge:analyze
description: >
  Perform a comprehensive analysis of an existing Claude Code skill. Examines
  all 6 dimensions (structure, triggers, quality, edges, efficiency, composability),
  shows both composite score and binary eval pass rate, and provides specific,
  actionable improvement suggestions ranked by impact.
---

# /skillforge:analyze

Perform a comprehensive analysis of a skill and identify top improvements.

## Instructions

1. Ask the user to identify the target skill path if not provided:
   "Which skill should I analyze? Give me the path to its SKILL.md."

2. Check if an eval suite exists. If not, suggest initialization:
   ```
   No eval suite found at eval-suite.json.
   Run /skillforge:init first to auto-generate one, then I can give you detailed metrics.
   For now, I'll do structural analysis only.
   ```

3. Read the SKILL.md file completely. Note:
   - Frontmatter (name, description)
   - Main sections (purpose, scope, "when to use", "when not to use")
   - Instructions or examples
   - Length and progressive disclosure

4. If a references/ directory exists, list and read each file for additional context.

5. Run structural analysis:
   ```bash
   bash scripts/analyze-skill.sh /path/to/SKILL.md
   ```

6. If eval suite exists, run comprehensive scoring:
   ```bash
   python3 scripts/score-skill.py \
     /path/to/SKILL.md \
     --eval-suite /path/to/skill/eval-suite.json \
     --json
   ```

7. If eval suite exists, run assertion checks:
   ```bash
   bash scripts/run-eval.sh \
     /path/to/SKILL.md \
     --eval-suite /path/to/skill/eval-suite.json \
     --no-runtime-auto
   ```

8. Score each dimension manually for nuance:

   - **Structure (15% weight)**: 
     * Frontmatter completeness, header organization, length proportionality
     * Examples and progressive disclosure (simple → complex)
     * Readability and logical flow

   - **Triggers (20% weight)**:
     * Description specificity: Can Claude detect when to use this?
     * Synonym coverage: Does it mention alternate phrasings?
     * Negative case clarity: Is it obvious when NOT to use it?
     * Actual trigger accuracy from eval suite (if available)

   - **Quality (25% weight)**:
     * Output correctness: Does the skill produce right answers?
     * Completeness: Does it cover the full scope?
     * Consistency: Are outputs reliable across variations?
     * Assertion pass rate from eval suite (if available)

   - **Edges (15% weight)**:
     * Error handling: What happens with invalid/missing input?
     * Ambiguity resolution: How does it handle unclear cases?
     * Graceful degradation: Does it fail cleanly or crash?
     * Edge case handling from eval suite (if available)

   - **Efficiency (15% weight)**:
     * Token usage: Are instructions concise?
     * Hedging elimination: Any unnecessary "maybe" language?
     * Example conciseness: Are examples right-sized?
     * Redundancy: Any repeated concepts?

   - **Composability (10% weight)**:
     * Scope boundaries: Clear handoff points to other skills?
     * Conflict risk: Could this clash with similar skills?
     * Dependency clarity: Does it state prerequisites?
     * Integration points: Can other skills call this cleanly?

9. Identify improvement opportunities by gap analysis:
   - For each dimension below 80: Why is it low?
   - For triggers <80: Which positive cases fail? Which negative cases trigger incorrectly?
   - For quality <80: Which test cases fail? What patterns emerge?
   - For edges <80: Which edge cases aren't handled? What assumptions are unstated?
   - For efficiency <80: Where are the token sinks? (long examples, hedging, etc.)
   - For composability <80: Are boundaries fuzzy? Are there conflict risks?

10. Rank improvements by estimated impact:
    - High impact: Low dimension score + High weight = big gain
    - Example: Triggers 60 × 20% weight = 12 composite points to gain
    - Medium impact: Medium score × Medium weight
    - Low impact: High score already OR low weight

11. If `--quick` flag provided, skip manual dimension scoring and only report:
    - Structural assessment (5 min, automated)
    - Eval assertion results (if suite exists)
    - Top 1-2 quick wins (token cleanup, clarity)

12. Present the analysis report:

    ```
    ## SkillForge Analysis: [skill-name]

    ### Composite Score: XX/100
    ### Pass Rate: X/Y assertions passing

    | Dimension | Score | Status | Key Finding |
    |-----------|-------|--------|-------------|
    | Structure | XX | ✓ | [1 sentence] |
    | Triggers | XX | ⚠️ | [1 sentence about trigger accuracy] |
    | Quality | XX | ✓ | [1 sentence about output correctness] |
    | Edges | XX | ✗ | [1 sentence about error handling gaps] |
    | Efficiency | XX | ⚠️ | [1 sentence about token usage] |
    | Composability | XX | ✓ | [1 sentence about scope clarity] |

    ### Top 3 Improvements (by estimated composite impact)

    **1. [Improvement title]** → +X composite points
    - Problem: [specific gap from analysis]
    - Solution: [concrete action, 1-2 sentences]
    - Effort: [quick (5 min) / medium (30 min) / involved (>1 hour)]
    - Example: [show what success looks like]

    **2. [Improvement title]** → +X composite points
    - Problem: [specific gap]
    - Solution: [concrete action]
    - Effort: [time estimate]
    - Example: [show result]

    **3. [Improvement title]** → +X composite points
    - Problem: [specific gap]
    - Solution: [concrete action]
    - Effort: [time estimate]
    - Example: [show result]

    ### Detailed Findings

    #### Structure (XX/100)
    [2-3 sentences on headers, organization, examples, progressive disclosure]

    #### Triggers (XX/100)
    [2-3 sentences on description specificity, synonym coverage, accuracy from evals]

    #### Quality (XX/100)
    [2-3 sentences on output correctness, completeness, assertion results]

    #### Edges (XX/100)
    [2-3 sentences on error handling, ambiguity resolution, edge case coverage]

    #### Efficiency (XX/100)
    [2-3 sentences on token usage, hedging, example conciseness]

    #### Composability (XX/100)
    [2-3 sentences on scope boundaries, conflict risks, integration clarity]

    ### Next Steps

    Run `/skillforge` to start the autonomous improvement loop.
    This will apply improvements one at a time, track results, and keep what works.
    ```

## Flags

- `--quick`: Fast structural-only analysis (5 min). Skips deep manual scoring.

## Notes

- Composite score is a weighted average: 15% structure + 20% triggers + 20% quality + 15% edges + 10% efficiency + 5% composability + 15% runtime (when enabled). Without runtime, weights are renormalized across the 6 static dimensions.
- Pass rate is the binary result: X assertions passing out of Y total (requires eval suite).
- If no eval suite exists, dimension scores are estimates based on manual review.
- Improvements are ranked by composite impact: (dimension_gap) × (dimension_weight).
- Each improvement includes concrete, actionable steps and an effort estimate.
