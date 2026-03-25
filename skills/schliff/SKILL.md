---
name: schliff
description: >
  Deterministic skill linter and scoring engine for Claude Code — the Ruff for
  SKILL.md files. 7-dimension structural scoring (structure, triggers, quality,
  edges, efficiency, composability, clarity) with anti-gaming detection, 60-70%
  rule-based patches, and cross-session episodic memory. An autoresearch loop
  that measures first, then fixes — not the other way around. Use for linting,
  scoring, and autonomously improving any Claude Code skill: trigger accuracy,
  output quality, edge coverage, token efficiency, composability, or custom
  metrics. Works with community, custom, project-local, or global skills.
  Trigger phrases: "make this skill better", "optimize my skill", "iterate on
  this skill overnight", "improve [metric] from X to Y", "audit skill",
  "review my skill", "harden skill", "benchmark skill", "lint my skill",
  "score my skill", or paste SKILL.md for auto-analysis. Also use when user
  shares skill without explicit instructions. Do NOT use for brand-new skills
  from scratch — use skill-creator first, then come to Schliff. Do NOT use for
  SQL query tuning. Do NOT use for prompt template authoring.
---

# Schliff — Skill Measurement & Iteration Framework

Constraint + clear metric + disciplined iteration = compounding gains. Each kept
improvement builds on the last. The composite score measures structural quality
(file organization, keyword coverage, eval suite breadth) — not runtime
effectiveness. Use `--runtime` to validate actual behavior.

## Quick Start (Only 2 Inputs Required)

```
/schliff
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
  → Commit with message: "schliff exp-N: [description]"
  → Run VERIFY command, compute PRIMARY METRIC
  → Metric improved? Keep. Worse? Revert. Error? Fix or skip.
  → Append to history/ dir with diffs
  → Loop continues until timeout or user stops
  CONSTRAINT: Fixed iterations prevent infinite loops; autonomous mode means
  NO prompts between iterations, just continuous improvement.
```

## When to Use

- **Skill not triggering properly** → Run `/schliff` on trigger-accuracy metric
- **Outputs are wrong or incomplete** → Set goal, metric is binary eval pass rate
- **Need to harden for edge cases** → Focus on edge-coverage metric
- **Skill too verbose** → Optimize token-efficiency metric
- **Don't know what's wrong** → Run `/schliff:analyze` for auto-discovery mode
- **Any custom goal** → Define GOAL, pick/create METRIC, set VERIFY command

## Interface: GOAL + METRIC + VERIFY

```
/schliff
Target: .claude/skills/my-skill/SKILL.md
Goal: Fix skill to handle deployment scenarios correctly
Metric: Binary eval pass rate %
Verify: bash scripts/run-eval.sh
Time budget: 2 hours
Iterations: 30
```

**Regression guards:** Set floor constraints to prevent one dimension from
regressing while improving another:

```bash
/schliff
Target: .claude/skills/deploy/SKILL.md
Goal: Maximize trigger accuracy
Metric: Trigger pass rate
Verify: python3 scripts/score-skill.py SKILL.md --json
Constraint: efficiency >= 80, composability >= 90
```

## Quality Dimensions (Defaults, Configurable via `--weights`)

| Dimension | Metric | How | Limitation |
|-----------|--------|-----|------------|
| **Structure** | Frontmatter lint score | `scripts/score-skill.py` (inline) | Measures file quality, not instruction correctness |
| **Trigger accuracy** | Keyword overlap with eval prompts | TF-IDF heuristic | Does not predict actual Claude triggering |
| **Output quality** | Eval suite assertion breadth | Test cases with assertions | Does not verify runtime output |
| **Edge coverage** | Edge-case definition coverage | Edge case test suite | Does not verify handling at runtime |
| **Token efficiency** | Instruction density (signal/noise) | `scripts/score-skill.py` | Cannot assess content usefulness |
| **Composability** | Scope boundary declarations | Static analysis | Cannot verify multi-skill interaction |
| **Clarity** *(default)* | Contradiction + ambiguity score | `score-skill.py` (opt-out: `--no-clarity`) | Pattern-based, not semantic |

See `references/metrics-catalog.md` for detailed rubrics and custom metric setup.

## Custom Metrics

Define any metric computable by a shell command returning a number:

```bash
Metric: "Time to first correct output (ms)"
Verify: time bash scripts/run-eval.sh | grep "passed"
```

Validate custom metrics by running them once before entering the loop.
See `references/metrics-catalog.md#custom` for setup and examples.

## Subcommands

| Command | Purpose |
|---------|---------|
| `/schliff:init` | Bootstrap eval-suite + baseline for any skill |
| `/schliff` | Autonomous loop with GOAL + METRIC |
| `/schliff:auto` | Self-driving auto-improve: apply deterministic patches in a loop |
| `/schliff:analyze` | Skill analysis, gaps, anti-patterns, baseline |
| `/schliff:bench` | Single evaluation run, current score |
| `/schliff:eval` | Run eval suite, show results |
| `/schliff:report` | Generate improvement summary + diffs |
| `/schliff:mesh` | Scan all skills for trigger overlap, broken handoffs, scope collisions |
| `/schliff:triage` | Cluster logged failures, auto-generate fixes |
| `/schliff:log-failure` | Manually log a skill failure for later triage |

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
5. Write descriptive commits: `schliff exp-7: add deployment edge cases`.
6. When stuck (5+ discards): re-read files, review history, try the opposite. This avoids local optima.
7. Never modify VERIFY during loop. The metric is fixed; the skill is the variable.
8. Log everything to `history/` — diffs, metric values, keep/discard status.
9. **Plateau guard:** Every 5 iterations, compare composite against 5 iterations ago.
   If delta < 1.0 over the window, switch strategy or suggest stopping.

## Cross-Session Learning

Reads `history/results.jsonl` at loop start. Parses keep/discard decisions per strategy type, computes success rates, prioritizes high-ROI strategies. Track diminishing returns: < 1 point over last 5 iterations triggers stop suggestion. Visualize with `scripts/progress.py`.

## Multi-File Skills

Handles SKILL.md + references/ trees. Reads full skill tree before each change. Extracts sections to `references/` when SKILL.md exceeds 400 lines. Verifies cross-file references resolve after each edit. For agent improvement: treat system prompt as SKILL.md, tool definitions as reference files.

## Discovery Mode (Auto-Gap Analysis)

Run `/schliff:analyze` without a GOAL. Schliff will:
1. Run all 7 dimension scorers on the target skill.
2. Identify the weakest dimension and its specific failure patterns.
3. Cluster eval failures to find systemic issues (e.g., "all false negatives share short prompts").
4. Propose a ranked list of improvements with estimated iteration cost.
5. Suggest GOAL + METRIC + VERIFY automatically. User confirms or overrides.

Use discovery mode when the user says "my skill needs work" without specifying what, e.g., `/schliff:analyze .claude/skills/deploy/SKILL.md`.

## Parallel Experimentation

Create 3 candidate changes on separate `git worktree` branches, run VERIFY on all 3, keep the highest improvement. Use when stuck (5+ discards) or gap > 15 points. Falls back to sequential if worktree unavailable.

## Noisy Metrics

When metrics fluctuate (>5%): run VERIFY 3 times, use median, keep only if improvement > 2x noise floor. Every 5 iterations, check composite against 5 iterations ago — revert to best checkpoint if composite dropped > 2 points despite individual keeps.

## Cost Tracking

`run-eval.sh --log` records duration, tokens, delta, status per run. Compute ROI: `delta / iterations_spent`. Stop when last 5 iterations gained < 0.5 points. Compare cross-session ROI via `progress.py --json`.

## Self-Evolving Eval Suites

Every 10 iterations: classify tests as mastered/blocked/flaky via `classify_eval_health()`. Reduce weight of mastered tests. Log eval mutations to `history/` separately. Run eval evolution BETWEEN sessions (preserves Rule 7: never modify VERIFY during loop).

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

## Lineage

`/skill-creator` → v1 → `/schliff` → autonomous grinding → merge. Roll back via `git log --oneline history/`. For crashing skills: use `systematic-debugging` instead, then return to Schliff.

## Requirements & Compatibility

Requires Python >= 3.9, Git >= 2.0, jq >= 1.6, Bash >= 4.0. No external Python
packages — standard library only. All `/schliff:*` commands are namespaced.
Safe to re-run — scorer is deterministic, auto-improve reverts on regression.
If scoring fails, returns structured error instead of crashing.

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
