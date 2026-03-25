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

Constraint + clear metric + disciplined iteration = compounding gains. The composite score measures structural quality (file organization, keyword coverage, eval suite breadth) — not runtime effectiveness. Use `--runtime` to validate actual behavior.

## Quick Start (Only 2 Inputs Required)

```bash
/schliff
Target: path/to/SKILL.md
Goal: Make the skill trigger correctly for deployment scenarios
```

Defaults: Metric=composite_score, Verify=score-skill.py, Iterations=30.

## Core Loop (NEVER Pauses)

```
INPUT: Skill path + GOAL + PRIMARY METRIC + VERIFY method + time budget
SETUP: Read ALL files → Analyze → Generate eval suite → Baseline (#0)
LOOP (N iterations, continues until goal met or budget exhausted):
  Exp N: Review skill + results + git history
  → Pick ONE atomic change (based on gaps + history)
  → Edit SKILL.md or references
  → Commit: "schliff exp-N: [description]"
  → Run VERIFY, compute PRIMARY METRIC
  → Improved? Keep. Worse? Revert. Error? Fix or skip.
  → Append to history/ with diffs
  CONSTRAINT: Fixed iterations prevent infinite loops; autonomous mode =
  NO prompts between iterations, just continuous improvement.
```

## When to Use

- **Skill not triggering** → Run `/schliff` on trigger-accuracy metric
- **Wrong/incomplete outputs** → Set goal, metric = binary eval pass rate
- **Harden for edge cases** → Focus on edge-coverage metric
- **Skill too verbose** → Optimize token-efficiency metric
- **Don't know what's wrong** → Run `/schliff:analyze` for auto-discovery
- **Any custom goal** → Define GOAL, pick/create METRIC, set VERIFY command

## Interface: GOAL + METRIC + VERIFY

```bash
/schliff
Target: .claude/skills/my-skill/SKILL.md
Goal: Fix skill to handle deployment scenarios correctly
Metric: Binary eval pass rate %
Verify: bash scripts/run-eval.sh
Time budget: 2 hours
Iterations: 30
```

**Regression guards** — prevent one dimension from regressing while improving another:

```bash
/schliff
Target: .claude/skills/deploy/SKILL.md
Goal: Maximize trigger accuracy
Metric: Trigger pass rate
Verify: python3 scripts/score-skill.py SKILL.md --json
Constraint: efficiency >= 80, composability >= 90
```

## Quality Dimensions (Configurable via `--weights`)

| Dimension | Metric | How | Limitation |
|-----------|--------|-----|------------|
| **Structure** | Frontmatter lint score | `score-skill.py` | File quality, not instruction correctness |
| **Trigger accuracy** | Keyword overlap | TF-IDF heuristic | Does not predict actual triggering |
| **Output quality** | Eval assertion breadth | Test cases | Does not verify runtime output |
| **Edge coverage** | Edge-case definitions | Edge test suite | Does not verify runtime handling |
| **Token efficiency** | Signal/noise density | `score-skill.py` | Cannot assess content usefulness |
| **Composability** | Scope boundaries | Static analysis | Cannot verify multi-skill interaction |
| **Clarity** *(default)* | Contradiction + ambiguity | `score-skill.py` (`--no-clarity` to opt out) | Pattern-based, not semantic |

See `references/metrics-catalog.md` for rubrics.

## Custom Metrics

Define any metric via a shell command returning a number:

```bash
Metric: "Time to first correct output (ms)"
Verify: time bash scripts/run-eval.sh | grep "passed"
```

Validate custom metrics by running once before the loop, for example by checking the return code.

## Subcommands

| Command | Purpose |
|---------|---------|
| `/schliff:init` | Bootstrap eval-suite + baseline |
| `/schliff` | Autonomous loop with GOAL + METRIC |
| `/schliff:auto` | Self-driving auto-improve: deterministic patches in a loop |
| `/schliff:analyze` | Skill analysis, gaps, anti-patterns, baseline |
| `/schliff:bench` | Single evaluation run, current score |
| `/schliff:eval` | Run eval suite, show results |
| `/schliff:report` | Generate improvement summary + diffs |
| `/schliff:mesh` | Scan skills for trigger overlap, broken handoffs, scope collisions |
| `/schliff:triage` | Cluster logged failures, auto-generate fixes |
| `/schliff:log-failure` | Log a skill failure for later triage |

## Before the Loop (Setup Phase)

1. Read ALL files — SKILL.md + references + related skills.
2. Parse GOAL + METRIC + VERIFY from input. Use defaults if unspecified.
3. Run baseline — Execute VERIFY, record initial metric as exp #0.
4. Generate eval suite if none exists. Use SKILL.md examples as seeds.
5. Validate eval suite — Run once, verify assertions parse correctly.
6. Show gap analysis with estimated iterations. Start NEVER-PAUSE mode on confirm.

## Autonomous Loop (Eight-Phase Protocol)

Per `references/improvement-protocol.md`. Immutable rules:

1. ONE change per experiment. Run `git diff` to verify scope, because atomic edits isolate causation.
2. Run VERIFY, check number, keep or discard. This prevents subjective drift.
3. Revert on regression: `git revert HEAD`. This ensures safe experimentation.
4. Re-read ALL files before each change. This prevents contradictions.
5. Descriptive commits: `schliff exp-7: add deployment edge cases`.
6. Stuck (5+ discards): re-read files, review history, try the opposite. This avoids local optima.
7. Never modify VERIFY during loop. Metric is fixed; skill is the variable.
8. Log everything to `history/` — diffs, metrics, keep/discard status.
9. **Plateau guard:** Every 5 iterations, compare composite against 5-back. Delta < 1.0 → switch strategy or stop.

## Cross-Session Learning

Read `history/results.jsonl` at loop start. Parse keep/discard per strategy, compute success rates, prioritize high-ROI strategies. < 1 point over 5 iterations triggers stop suggestion. Visualize with `scripts/progress.py`.

## Multi-File Skills

Read full skill tree before each change. Extract sections to `references/` when SKILL.md exceeds 400 lines. Verify cross-file references after each edit. For agents: treat system prompt as SKILL.md, tool definitions as references.

## Discovery Mode (Auto-Gap Analysis)

Run `/schliff:analyze` without a GOAL:
1. Run all 7 dimension scorers.
2. Identify weakest dimension and failure patterns.
3. Cluster eval failures for systemic issues (e.g., "all false negatives share short prompts").
4. Propose ranked improvements with estimated iteration cost.
5. Suggest GOAL + METRIC + VERIFY. User confirms or overrides.

Use when user says "my skill needs work" without specifying what, e.g., `/schliff:analyze path/to/SKILL.md`.

## Parallel Experimentation

Create 3 candidates on separate `git worktree` branches, run VERIFY on all, keep highest improvement. Use when stuck (5+ discards) or gap > 15 points. Fallback to sequential if worktree unavailable.

## Noisy Metrics

When metrics fluctuate (>5%): run VERIFY 3x, use median, keep only if improvement > 2x noise floor. Revert to best checkpoint if composite dropped > 2 points despite individual keeps.

## Cost Tracking

`run-eval.sh --log` records duration, tokens, delta, status per run. ROI = `delta / iterations_spent`. Stop when last 5 iterations gained < 0.5 points. Cross-session ROI via `progress.py --json`.

## Self-Evolving Eval Suites

Every 10 iterations: classify tests as mastered/blocked/flaky via `classify_eval_health()`. Reduce mastered test weight. Log mutations to `history/`. Run eval evolution BETWEEN sessions (preserves Rule 7).

## Improvement Strategies (Dynamic)

Select based on gap analysis. Pick first dimension with gap > 10 points:

1. Fix structural issues — Run `python3 scripts/score-skill.py SKILL.md --json`.
2. Expand triggers — Add synonyms, edge cases, negative boundaries.
3. Add input/output examples — Write 3+ concrete before/after pairs.
4. Add edge-case handling — Test with malformed input, missing context, empty files.
5. Optimize density — Remove redundancy, compress verbose phrasing.
6. Extract references — Move deep content to `references/`.
7. Verify composability — Check handoff points, run with adjacent skills.

See `references/metrics-catalog.md` for patterns per dimension.

## Example Session

```bash
Goal: Trigger accuracy from 60% to 90%
Verify: bash scripts/run-eval.sh | grep "PASS" | wc -l

Exp 1: Add synonyms to description → 65% → Keep
Exp 2: Add negative trigger examples → 70% → Keep
Exp 3: Compress verbose setup section → 68% → Discard (revert)
Exp 4: Add edge case for partial audit → 75% → Keep
```

Parse `history/results.jsonl` between sessions. Compare keep rates to prioritize high-ROI changes next session.

## Lineage

`/skill-creator` → v1 → `/schliff` → autonomous grinding → merge. Roll back via `git log --oneline history/`. For crashing skills: use `systematic-debugging` first, then Schliff.

## Requirements

Requires Python >= 3.9, Git >= 2.0, jq >= 1.6, Bash >= 4.0. Standard library only. All `/schliff:*` commands are namespaced. Deterministic scorer, safe to re-run. If scoring fails, returns structured error.

## Files

Run `ls -R` in skill directory. Run `python3 scripts/score-skill.py SKILL.md --json` for scores. Key files:
- `scripts/init-skill.py` — Bootstrap eval-suite (`--json --dry-run`)
- `scripts/generate-report.py` — Shareable improvement report
- `scripts/score-skill.py` — Dimension scores incl. runtime (`--diff --clarity --weights`)
- `scripts/text-gradient.py` — Invert scorer issues into fix list (`--json --top N --apply --dry-run`)
- `scripts/auto-improve.py` — Autonomous loop (`--max-iterations N --dry-run --resume`)
- `scripts/skill-mesh.py` — Multi-skill conflict detection (`--incremental`)
- `scripts/meta-report.py` — Strategy predictor + auto-calibration
- `scripts/episodic-store.py` — Cross-session memory (`--store --recall --synthesize`)
- `scripts/parallel-runner.py` — Worktree parallel experimentation (`--strategies --auto`)
- `scripts/runtime-evaluator.py` — Invoke Claude with test prompts, check output
- `scripts/analyze-skill.sh` — Legacy linter (score-skill.py has this built-in)
- `scripts/run-eval.sh` — Run eval suite (`--runtime` auto-enabled if claude CLI available)
- `scripts/progress.py` — Convergence charts + strategy analysis (`--emit-meta`)
- `hooks/session-injector.js` — SessionStart hook: surfaces untriaged failures
- `references/improvement-protocol.md` — Full 9-phase loop spec
- `references/metrics-catalog.md` — Scoring rubrics + custom metrics
- `templates/eval-suite-template.json` — Eval skeleton for new skills
