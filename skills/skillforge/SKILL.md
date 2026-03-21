---
name: skillforge
description: >
  Disciplined skill improvement and measurement framework — the autoresearch
  loop for Claude Code skills. Define a GOAL, primary METRIC, and VERIFY
  method; SkillForge iterates autonomously with fixed time budgets, mechanical
  scoring, and NEVER pauses. Use for improving any skill on any domain: trigger
  accuracy, output quality, edge coverage, token efficiency, composability, or
  custom metrics. Works with community, custom, project-local, or global
  skills. Trigger phrases: "make this skill better", "optimize my skill",
  "iterate on this skill overnight", "improve [metric] from X to Y", "audit
  skill", "review my skill", "harden skill", "benchmark skill", or paste
  SKILL.md for auto-analysis. Also use when user shares skill without explicit
  instructions. Do NOT use for brand-new skills from scratch — use
  skill-creator first, then come to SkillForge.
---

# SkillForge — Skill Measurement & Iteration Framework

Constraint + clear metric + disciplined iteration = compounding gains. Each kept
improvement builds on the last. The composite score measures structural quality
(file organization, keyword coverage, eval suite breadth) — not runtime
effectiveness. Use `--runtime` to validate actual behavior.

## Quick Start (Only 2 Inputs Required)

```
/skillforge
Target: path/to/SKILL.md
Goal: Make the skill trigger correctly for deployment scenarios
```

Defaults: Metric=composite_score, Verify=score-skill.py, Iterations=30.

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

```
/skillforge
Target: .claude/skills/my-skill/SKILL.md
Goal: Fix skill to handle deployment scenarios correctly
Metric: Binary eval pass rate %
Verify: bash scripts/run-eval.sh
Time budget: 2 hours
Iterations: 30
```

**Regression guards:** Set floor constraints to prevent one dimension from
regressing while improving another:

```
/skillforge
Target: .claude/skills/deploy/SKILL.md
Goal: Maximize trigger accuracy
Metric: Trigger pass rate
Verify: python3 scripts/score-skill.py SKILL.md --json
Constraint: efficiency >= 80, composability >= 90
```

Use constraints to prevent dimension degradation during optimization.

## Quality Dimensions (Defaults, Configurable via `--weights`)

| Dimension | Metric | How | Limitation |
|-----------|--------|-----|------------|
| **Structure** | Frontmatter lint score | `scripts/score-skill.py` (inline) | Measures file quality, not instruction correctness |
| **Trigger accuracy** | Keyword overlap with eval prompts | TF-IDF heuristic | Does not predict actual Claude triggering |
| **Output quality** | Eval suite assertion breadth | Test cases with assertions | Does not verify runtime output |
| **Edge coverage** | Edge-case definition coverage | Edge case test suite | Does not verify handling at runtime |
| **Token efficiency** | Instruction density (signal/noise) | `scripts/score-skill.py` | Cannot assess content usefulness |
| **Composability** | Scope boundary declarations | Static analysis | Cannot verify multi-skill interaction |
| **Clarity** *(opt-in)* | Contradiction + ambiguity score | `score-skill.py --clarity` | Pattern-based, not semantic |

**Important:** These dimensions measure structural quality — how well-formed your skill file
is. They do NOT measure runtime effectiveness. Use `scripts/runtime-evaluator.py` to invoke
Claude with test prompts and check actual output against assertions.
See `references/metrics-catalog.md` for detailed rubrics and custom metric setup.

## Custom Metrics

Define any metric computable by a shell command returning a number:

```
Metric: "Time to first correct output (ms)"
Verify: time bash scripts/run-eval.sh | grep "passed"
```

Validate custom metrics by running them once before entering the loop.
See `references/metrics-catalog.md#custom` for setup and examples.

## Subcommands

| Command | Purpose |
|---------|---------|
| `/skillforge:init` | Bootstrap eval-suite + baseline for any skill |
| `/skillforge` | Autonomous loop with GOAL + METRIC |
| `/skillforge:auto` | Self-driving auto-improve: apply deterministic patches in a loop |
| `/skillforge:analyze` | Skill analysis, gaps, anti-patterns, baseline |
| `/skillforge:bench` | Single evaluation run, current score |
| `/skillforge:eval` | Run eval suite, show results |
| `/skillforge:report` | Generate improvement summary + diffs |
| `/skillforge:mesh` | Scan all skills for trigger overlap, broken handoffs, scope collisions |
| `/skillforge:mesh-evolve` | Mesh + generate fix actions (negative boundaries, stubs) |
| `/skillforge:predict` | Predict best strategy before trying (from cross-session data) |
| `/skillforge:recall` | Recall relevant past episodes from episodic memory |
| `/skillforge:triage` | Cluster logged failures, auto-generate fixes |
| `/skillforge:log-failure` | Manually log a skill failure for later triage |

## Before the Loop (Setup Phase)

1. Read ALL files — SKILL.md + all references + related skills. Extract context.
2. Parse GOAL + METRIC + VERIFY from user input. Use defaults if not specified.
3. Run baseline — Execute VERIFY command, record initial metric as exp #0.
4. Generate eval suite if none exists. Use examples from SKILL.md as seeds.
5. Validate eval suite — Run it once, verify assertions parse correctly.
6. Show gap analysis with estimated iterations. Start NEVER-PAUSE mode on confirm.

## Autonomous Loop (Eight-Phase Protocol)

Each iteration follows `references/improvement-protocol.md`. Immutable rules:

1. ONE change per experiment. Run `git diff` to verify scope, because atomic edits isolate causation.
2. Mechanical verification only. Run VERIFY, check the number, keep or discard. This prevents subjective drift.
3. Revert on regression: `git revert HEAD`. This ensures safe experimentation.
4. Re-read ALL files before each change. This prevents contradictions.
5. Write descriptive commits: `skillforge exp-7: add deployment edge cases`.
6. When stuck (5+ discards): re-read files, review history, try the opposite. This avoids local optima.
7. Never modify VERIFY during loop. The metric is fixed; the skill is the variable.
8. Log everything to `history/` — diffs, metric values, keep/discard status.
9. **Plateau guard:** Every 5 iterations, compare composite against 5 iterations ago.
   If delta < 1.0 over the window, switch strategy or suggest stopping.

## Cross-Session Learning

SkillForge reads `history/results.jsonl` at loop start. Extract patterns from past runs:
1. Parse all previous keep/discard decisions with their change types.
2. Compute success rate per strategy (e.g., "synonym expansion: 80% keep rate").
3. Prioritize strategies with highest historical success rate for this skill.
4. Track diminishing returns: if last 5 iterations gained < 1 point total, suggest stopping.

Use `scripts/progress.py` to visualize convergence curves and detect plateaus.

## Agent + Multi-File Skill Improvement

SkillForge handles skills that span multiple files (SKILL.md + references/):
1. Read the full skill tree before each change. Build a file dependency map.
2. When a change requires a new reference file, create it and add a pointer from SKILL.md.
3. When SKILL.md exceeds 400 lines, extract the largest section to `references/`.
4. Verify all cross-file references resolve after each change.

For agent improvement (not just skills): treat the agent's system prompt as SKILL.md
and tool definitions as reference files. Execute the same loop on agent configs.

## Discovery Mode (Auto-Gap Analysis)

Run `/skillforge:analyze` without a GOAL. SkillForge will:
1. Run all 6 dimension scorers on the target skill.
2. Identify the weakest dimension and its specific failure patterns.
3. Cluster eval failures to find systemic issues (e.g., "all false negatives share short prompts").
4. Propose a ranked list of improvements with estimated iteration cost.
5. Suggest GOAL + METRIC + VERIFY automatically. User confirms or overrides.

Use discovery mode when the user says "my skill needs work" without specifying what.

## Parallel Experimentation (Try 3, Keep Best) — Planned

For iterations where multiple plausible changes exist:
1. Create 3 candidate changes on separate git branches using `git worktree`.
2. Run VERIFY on all 3 branches independently.
3. Keep the branch with the highest metric improvement. Discard the other two.
4. Fall back to sequential mode if git worktree is unavailable.

Use parallel mode when stuck (5+ sequential discards) or when the gap-to-target
is large (>15 points). Explores 3x more search space per iteration.

## Noisy Metric + Interaction Effects

When metrics fluctuate (±5%): run VERIFY 3 times, use median, keep only if
improvement > 2 * noise floor (detected from first 3 baseline runs).

Guard against interaction effects: every 5 iterations, compare composite against
5 iterations ago. If composite dropped > 2 points despite individual keeps, revert
to best-in-window checkpoint and re-apply only non-conflicting keeps.

## Cost Tracking + ROI

Track improvement efficiency to stop when returns diminish:
1. `run-eval.sh --log` records `duration_ms`, `tokens_estimated`, `delta`, and `status` per run.
2. Compute ROI: `delta_metric / iterations_spent` after each keep.
3. Stop when ROI drops below threshold (e.g., last 5 iterations < 0.5 points gained).
4. Use `progress.py --json` to compare cross-session ROI from logged data.

Stop grinding when ROI drops below threshold to prevent wasted iterations.

## Self-Evolving Eval Suites

After every 10 iterations, analyze eval suite effectiveness:
1. Classify tests as "mastered", "blocked", or "flaky" via `classify_eval_health()`.
2. Reduce weight of mastered tests — they no longer discriminate quality changes.
3. Auto-generation of new test cases: classification implemented, auto-generation planned.
4. Log eval mutations to `history/` separately from skill changes.

Run eval evolution BETWEEN sessions, not during the loop, because this preserves
Rule 7 (never modify VERIFY during loop) while improving test coverage.

## Improvement Strategies (Dynamic)

Select strategy based on gap analysis, not fixed priority. Check dimensions in
this order and pick the first with a gap > 10 points from target:

1. Fix structural issues — Run `python3 scripts/score-skill.py SKILL.md --json` to detect gaps.
2. Expand trigger description — Add synonyms, edge cases, negative boundaries.
3. Add input/output examples — Write 3+ concrete before/after pairs per feature.
4. Add edge-case handling — Test with malformed input, missing context, empty files.
5. Optimize token density — Remove redundancy, compress verbose phrasing.
6. Extract reference files — Move deep content from SKILL.md to `references/`.
7. Verify composability — Check handoff points and run with adjacent skills.

See `references/metrics-catalog.md` for patterns and anti-patterns per dimension.

## Example Session

```
Goal: Trigger accuracy from 60% to 90%
Verify: bash scripts/run-eval.sh | grep "PASS" | wc -l

Exp 1: Add synonyms to description → 65% → Keep
Exp 2: Add negative trigger examples → 70% → Keep
Exp 3: Compress verbose setup section → 68% → Discard (revert)
Exp 4: Add edge case for partial audit → 75% → Keep
```

Parse `history/results.jsonl` between sessions to extract which strategy types succeed.
Compare keep rates per strategy to prioritize high-ROI changes in the next session.

## Skill Genealogy + Handoff

Track lineage: `/skill-creator` → v1 → `/skillforge` → autonomous grinding → merge.
Roll back to any version: `git log --oneline history/` shows the full lineage.

Create new skills with `skill-creator`. For crashing skills, suggest using
`systematic-debugging` first, then return to SkillForge for iteration.

## Files

Run `ls -R` in the skill directory. Run `python3 scripts/score-skill.py SKILL.md --json` for current scores. Key files:
- `scripts/init-skill.py` — Bootstrap eval-suite from any SKILL.md (`--json`, `--dry-run`)
- `scripts/generate-report.py` — Shareable markdown improvement report
- `scripts/score-skill.py` — Compute dimension scores incl. runtime (`--diff`, `--clarity`, `--weights`)
- `scripts/text-gradient.py` — Invert scorer issues into fix list (`--json`, `--top N`, `--apply`, `--dry-run`)
- `scripts/auto-improve.py` — Self-driving autonomous loop (`--max-iterations N`, `--dry-run`, `--resume`)
- `scripts/skill-mesh.py` — Multi-skill conflict detection + evolution actions (`--incremental`)
- `scripts/meta-report.py` — Strategy predictor + auto-calibration + correlation insights
- `scripts/episodic-store.py` — Cross-session learning memory (`--store`, `--recall`, `--synthesize`)
- `scripts/parallel-runner.py` — Worktree-based parallel experimentation (`--strategies`, `--auto`)
- `scripts/runtime-evaluator.py` — Invoke Claude with test prompts, check real output
- `scripts/analyze-skill.sh` — Legacy standalone structural linter (score-skill.py has this built-in)
- `scripts/run-eval.sh` — Run eval suite (auto-enables `--runtime` if claude CLI is available)
- `scripts/progress.py` — Convergence charts + strategy analysis + episode emit (`--emit-meta`)
- `hooks/session-injector.js` — SessionStart hook: surfaces untriaged failures
- `references/improvement-protocol.md` — Full 9-phase autonomous loop spec
- `references/metrics-catalog.md` — Scoring rubrics + custom metric setup
- `templates/eval-suite-template.json` — Eval skeleton for new skills
