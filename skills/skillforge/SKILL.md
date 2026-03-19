---
name: skillforge
description: >
  Autonomous skill improvement engine — the autoresearch loop for Claude Code
  skills. Define a GOAL, primary METRIC, and VERIFY method; SkillForge iterates
  autonomously with fixed time budgets, mechanical scoring, and NEVER pauses.
  Use for improving any skill on any domain: trigger accuracy, output quality,
  edge coverage, token efficiency, composability, or custom metrics. Works with
  community, custom, project-local, or global skills. Trigger phrases: "make
  this skill better", "optimize my skill", "iterate on this skill overnight",
  "improve [metric] from X to Y", "audit skill", "review my skill", "harden
  skill", "benchmark skill", or paste SKILL.md for auto-analysis. Also use when
  user shares skill without explicit instructions. Do NOT use for brand-new
  skills from scratch — use skill-creator first, then come to SkillForge.
---

# SkillForge — Autonomous Skill Improvement Engine

**Why this works:** Constraint + clear metric + autonomous iteration = compounding gains.
Small atomic changes with mechanical verification compound because each kept improvement
builds on the last — like gradient descent for skill quality.

Based on [Karpathy's autoresearch](https://github.com/karpathy/autoresearch),
[Uditgoenka's generalized autoresearch](https://github.com/uditgoenka/autoresearch-general),
and [Olelehmann's binary eval framework](https://github.com/olelehmann/skill-eval).

## Quick Start (Simplest Usage)

```
/skillforge
Target: path/to/SKILL.md
Goal: Make the skill trigger correctly for deployment scenarios
```

SkillForge will auto-select metrics, generate evals, and run 30 iterations.
Or customize with explicit metric + time budget.

## Core Loop (NEVER Pauses)

```
INPUT: Skill path + GOAL + PRIMARY METRIC + VERIFY method + time budget
SETUP: Read ALL files → Analyze → Generate eval suite → Baseline (#0)
LOOP (fixed time or N iterations, continues until goal met or budget exhausted):
  Exp N: Review skill + results + git history
  → Pick ONE atomic change (based on gaps + what worked/failed in history)
  → Edit SKILL.md or references
  → Commit with message: "skillforge exp-N: [description]"
  → Run VERIFY command, compute PRIMARY METRIC
  → Metric improved? Keep. Worse? Revert. Error? Fix or skip.
  → Append to history/ dir with diffs
  → Loop continues until timeout or user stops
  CONSTRAINT: Fixed iterations prevent infinite loops; autonomous mode means
  NO prompts between iterations, just continuous improvement.
```

## When to Use

- **Skill not triggering properly** → Run `/skillforge` on trigger-accuracy metric
- **Outputs are wrong or incomplete** → Set goal, metric is binary eval pass rate
- **Need to harden for edge cases** → Focus on edge-coverage metric
- **Skill too verbose** → Optimize token-efficiency metric
- **Don't know what's wrong** → Run `/skillforge:analyze` for auto-discovery mode
- **Any custom goal** → Define GOAL, pick/create METRIC, set VERIFY command

## Interface: GOAL + METRIC + VERIFY

Instead of always using 6 dimensions, start with user intent:

```
/skillforge
Target: .claude/skills/my-skill/SKILL.md
Goal: Fix skill to handle deployment scenarios correctly
Metric: Binary eval pass rate % (custom: run eval suite, count passing tests)
Verify: bash scripts/run-eval.sh
Time budget: 2 hours
Iterations: 30
```

The 6 default dimensions are available as presets, but **not required**.

## Quality Dimensions (Defaults, Customizable)

| Dimension | Metric | How | Pass Rate |
|-----------|--------|-----|-----------|
| **Structure** | Frontmatter lint score | `scripts/analyze-skill.sh` | ≥ 90% |
| **Trigger accuracy** | Positive/negative trigger pass rate | Eval suite, count matches | ≥ 85% |
| **Output quality** | Binary eval pass rate | Test cases with assertions | ≥ 90% |
| **Edge coverage** | Edge-case test pass rate | Malformed input, corner cases | ≥ 80% |
| **Token efficiency** | Instruction density (words per feature) | `scripts/score-skill.py` | ≤ target |
| **Composability** | Cross-skill conflict tests | Run with other skills | 0 conflicts |

See `references/metrics-catalog.md` for detailed rubrics and custom metric setup.

## Custom Metrics

SkillForge supports any measurable metric:

```
Metric: "Time to first correct output (ms)"
Verify: time bash scripts/run-eval.sh | grep "passed"
Better: lower (invert scoring if needed)

Metric: "Coverage of domain-specific vocabulary"
Verify: grep -c "technical_term" eval-results.txt
Better: higher
```

Metrics must be computable by a shell command returning a number.
See `references/metrics-catalog.md#custom` for examples.

## Subcommands

| Command | Purpose |
|---------|---------|
| `/skillforge` | Autonomous loop with GOAL + METRIC |
| `/skillforge:analyze` | Skill analysis, gaps, anti-patterns, baseline |
| `/skillforge:bench` | Single evaluation run, current score |
| `/skillforge:eval` | Run eval suite, show results |
| `/skillforge:report` | Generate improvement summary + diffs |

## Before the Loop (Setup Phase)

1. Read ALL files — SKILL.md + all references + related skills. Extract context.
2. Parse GOAL + METRIC + VERIFY from user input. Use defaults if not specified.
3. Run baseline — Execute VERIFY command, record initial metric as exp #0.
4. Generate eval suite if none exists. Use examples from SKILL.md as seeds.
5. Validate eval suite — Run it once, verify assertions parse correctly.
6. Show gap analysis with estimated iterations. Start NEVER-PAUSE mode on confirm.

## Autonomous Loop (Eight-Phase Protocol)

Each iteration follows `references/improvement-protocol.md`. Immutable rules:

1. Make ONE change per experiment. Run `git diff` to verify scope before commit, because atomic edits isolate what caused improvement.
2. Use mechanical verification only. Run VERIFY command, check the number, decide keep/discard. This prevents subjective drift over iterations.
3. Revert on regression: `git revert HEAD`. This enables bold experimentation because rollback is safe.
4. Read ALL files before each change. This prevents contradictions and ensures history informs the next change.
5. Write descriptive commits: `skillforge exp-7: add deployment edge cases`. Git history is memory — past diffs reveal successful patterns.
6. When stuck (5+ discards): Re-read files, review history, try structural changes or the opposite of what failed. This avoids local optima.
7. Never modify VERIFY during loop. The metric is fixed; the skill is the variable. Otherwise results are incomparable.
8. Log everything to `history/` — diffs, metric values, status. This ensures future iterations analyze what worked.

## History Directory (Experiment Diffs)

SkillForge maintains a `history/` subdirectory with timestamped diffs:

```
skillforge/history/
├── exp-001-baseline.txt
├── exp-001-to-002.diff
├── exp-002-to-003.diff
├── exp-003-baseline.json     ← scores only, no revert
├── results.jsonl             ← experiment log (JSONL)
```

Result lines: `exp | commit | metric | status | description`

Diffs enable future runs to spot patterns: "what improved metric in the past?"

## Discovery Mode (Auto-Gap Analysis)

Run `/skillforge:analyze` without a GOAL. SkillForge will:
1. Run all 6 dimension scorers on the target skill.
2. Identify the weakest dimension and its specific failure patterns.
3. Cluster eval failures to find systemic issues (e.g., "all false negatives share short prompts").
4. Propose a ranked list of improvements with estimated iteration cost.
5. Suggest GOAL + METRIC + VERIFY automatically. User confirms or overrides.

Use discovery mode when the user says "my skill needs work" without specifying what.

## Parallel Experimentation (Try 3, Keep Best)

For iterations where multiple plausible changes exist:
1. Create 3 candidate changes on separate git branches using `git worktree`.
2. Run VERIFY on all 3 branches independently.
3. Keep the branch with the highest metric improvement. Discard the other two.
4. Fall back to sequential mode if git worktree is unavailable.

Use parallel mode when stuck (5+ sequential discards) or when the gap-to-target
is large (>15 points). This is 3x faster than sequential experimentation because
each iteration explores more of the search space.

## Noisy Metric Handling

When metrics fluctuate (±5% across runs), use multi-run averaging:
1. Run VERIFY 3 times per iteration. Use the median score.
2. Apply a significance threshold: keep only if improvement > 2 * noise floor.
3. Detect noise floor automatically from the first 3 baseline runs.

Use this when the VERIFY command involves LLM output or timing-dependent checks.

## Improvement Strategies (Dynamic)

Select strategy based on gap analysis, not fixed priority. Check dimensions in
this order and pick the first with a gap > 10 points from target:

1. Fix structural issues — Run `bash scripts/analyze-skill.sh` to detect gaps.
2. Expand trigger description — Add synonyms, edge cases, negative boundaries.
3. Add input/output examples — Write 3+ concrete before/after pairs per feature.
4. Add edge-case handling — Test with malformed input, missing context, empty files.
5. Optimize token density — Remove redundancy, compress verbose phrasing.
6. Extract reference files — Move deep content from SKILL.md to `references/`.
7. Verify composability — Check handoff points and run with adjacent skills.

See `references/skill-patterns.md` for patterns + anti-patterns.

## Example: Real Improvement Session

```
Goal: Make "audit" trigger work for all audit-related requests
Metric: Binary eval pass rate (run eval suite, count passing tests)
Verify: bash scripts/run-eval.sh | grep "PASS" | wc -l
Time budget: 1 hour
Iterations: 20

Baseline (exp #0): 60% (12/20 tests pass)

Exp 1: Add synonyms to description
  Change: "audit" → "audit, review, assess, inspect, evaluate"
  Result: 65% (13/20)
  Keep: ✓

Exp 2: Add negative trigger examples
  Change: Add examples of when NOT to trigger
  Result: 70% (14/20)
  Keep: ✓

Exp 3: Add edge case for partial audit
  Change: Handle "just check the trigger accuracy" (partial audit)
  Result: 75% (15/20)
  Keep: ✓

[Continue until goal met or iterations exhausted]
```

## Skill-Creator Handoff

SkillForge and `skill-creator` are complementary:

- **skill-creator** → v1 draft, initial tests, human review
- **SkillForge** → autonomous grinding, 30+ iterations, production quality

**Workflow:**
1. `/skill-creator` → draft, manual iterations, user confirms "ready to grind"
2. `/skillforge` → 30+ autonomous iterations, mechanical metrics, history
3. `/skillforge:report` → review changes, approve, merge
4. If new capabilities needed → back to `/skill-creator`

SkillForge never creates skills from scratch. If the user wants a new skill
from scratch, instead use `skill-creator`. If the user wants to debug a skill
that crashes, suggest using the `systematic-debugging` skill first, then return
to SkillForge for iteration.

## Files in This Skill

```
skillforge/
├── SKILL.md                          ← You are here
├── references/
│   ├── improvement-protocol.md       ← Detailed 8-phase loop
│   ├── metrics-catalog.md            ← Scoring rubrics + custom metrics
│   └── skill-patterns.md             ← Patterns, anti-patterns, examples
├── scripts/
│   ├── analyze-skill.sh              ← Structure lint
│   ├── score-skill.py                ← Dimension scoring
│   ├── run-eval.sh                   ← Unified eval runner
│   └── progress.py                   ← Progress tracking + ASCII charts
├── templates/
│   ├── eval-suite-template.json      ← Eval skeleton
│   └── improvement-log-template.jsonl ← History template (JSONL)
└── history/                          ← Experiment diffs + results
    └── results.jsonl
```
