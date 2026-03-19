---
name: skillforge
description: >
  Autonomous skill improvement engine — the autoresearch loop for Claude Code
  skills. Takes any SKILL.md as input and iteratively improves it with 6
  measurable dimensions: structure, trigger accuracy, output quality, edge
  coverage, token efficiency, composability. Use this skill whenever the user
  mentions improving, optimizing, auditing, benchmarking, debugging, or
  iterating on any Claude Code or Codex skill. Trigger phrases include:
  "make this skill better", "optimize my skill", "my skill doesn't trigger",
  "skill output is wrong", "audit skill quality", "run skill evals",
  "improve trigger accuracy", "skill needs work", "harden this skill",
  "benchmark my skill", "skill quality score". Also use when someone says
  "the skill isn't working right", "can you review my skill", "iterate on
  this skill overnight", or pastes a SKILL.md asking for feedback. Use even
  when the user just shares a SKILL.md without explicit instructions — they
  likely want analysis or improvement. Works with any skill: custom, community,
  built-in, project-local, or global. Do NOT use for creating brand-new skills
  from scratch (that's skill-creator's job) — SkillForge improves existing ones.
  After skill-creator builds v1, SkillForge grinds it to production quality.
---

# SkillForge — Autonomous Skill Improvement Engine

Based on [Karpathy's autoresearch](https://github.com/karpathy/autoresearch) —
the principle that **constraint + mechanical metric + autonomous iteration = compounding gains**,
applied to the meta-problem of improving Claude Code skills themselves.

## Core Loop

```
INPUT: Path to target skill (SKILL.md + references/)
SETUP: Analyze → Generate eval suite → Establish baseline score
LOOP (FOREVER or N iterations):
  1. Review skill + eval results + improvement log
  2. Pick ONE improvement (based on gap analysis + what worked/failed)
  3. Apply atomic change to SKILL.md or references
  4. Git commit (before verification)
  5. Run eval suite → compute quality score
  6. Score improved → keep. Worse → git revert. Crash → fix or skip.
  7. Log result to skillforge-results.tsv
  8. Repeat. NEVER STOP unless goal met or user interrupts.
```

## When to Use

- **Skill not triggering** → Run `/skillforge:analyze` then `/skillforge` to fix description
- **Skill output quality low** → Run `/skillforge` with output-quality metric
- **New skill needs hardening** → Run `/skillforge` to add edge cases + examples
- **Skill too verbose / too terse** → Run `/skillforge` with token-efficiency metric
- **Community skill needs adaptation** → Analyze → Fork → Improve

## Quick Start

```
/skillforge
Target: .claude/skills/my-skill/SKILL.md
Goal: Improve trigger accuracy from ~60% to 90%+
```

Or with more control:

```
/skillforge
Target: ~/.claude/skills/deploy/SKILL.md
Goal: Improve output quality — all test cases produce correct deployments
Metric: eval pass rate % (higher is better)
Iterations: 30
```

## Quality Dimensions (Metrics)

SkillForge scores skills across 6 measurable dimensions:

| Dimension | What It Measures | How |
|-----------|-----------------|-----|
| **Structure** | Frontmatter, progressive disclosure, file organization | Automated lint script |
| **Trigger accuracy** | Does the skill activate for the right prompts? | Eval suite with positive/negative triggers |
| **Output quality** | Does following the skill produce correct results? | Test cases with assertions |
| **Edge coverage** | Does the skill handle unusual inputs gracefully? | Edge-case eval suite |
| **Token efficiency** | Minimal instructions for maximum effect | Instruction density scoring |
| **Composability** | Works well with other skills, doesn't conflict | Cross-skill interference tests |

Read `references/metrics-catalog.md` for detailed scoring rubrics.

## Subcommands

| Command | Purpose |
|---------|---------|
| `/skillforge` | Full autonomous improvement loop |
| `/skillforge:analyze` | Deep skill analysis — structure, gaps, anti-patterns |
| `/skillforge:bench` | Benchmark current skill quality (baseline) |
| `/skillforge:eval` | Run evaluation suite against skill |
| `/skillforge:report` | Generate improvement report with recommendations |

## Setup Phase (Before Loop)

1. **Read target skill** — Load SKILL.md + all references, understand intent
2. **Analyze structure** — Run `scripts/analyze-skill.sh` for structural lint
3. **Generate eval suite** — Create test prompts (positive triggers, negative triggers, edge cases)
4. **Establish baseline** — Score all 6 dimensions, record as iteration #0
5. **Identify top gaps** — Rank dimensions by improvement potential
6. **Confirm with user** — Show analysis + proposed improvement plan, then begin

## Autonomous Loop Protocol

Each iteration follows the 8-phase protocol. Read `references/improvement-protocol.md`
for the detailed phase-by-phase instructions.

**Critical rules during the loop:**

1. **ONE change per iteration** — When something breaks, you need to know exactly why. Bundled changes make rollback a guessing game and waste iterations.
2. **Mechanical verification only** — "Looks better" kills autonomous loops. If you can't score it with a command, the loop can't learn from it. Run the eval suite, compare numbers.
3. **Automatic rollback** — The loop's power comes from safe experimentation. `git revert` on regression means you can try bold changes without risk. This is what makes overnight runs possible.
4. **Simplicity wins** — LLMs pay attention tax on every token. Equal quality with fewer instructions is strictly better because it leaves more context window for the user's actual task.
5. **Git is memory** — Commits are how the agent learns patterns across iterations. Descriptive messages like `skillforge: triggers add deployment synonyms` let it read history and avoid repeating failed approaches.
6. **When stuck after 5 discards** — Re-read ALL files fresh, review the results log for patterns, try combining two near-misses, or try the opposite of what hasn't been working. Plateaus often break with structural changes, not incremental tweaks.
7. **Never modify the eval suite during the loop** — Changing the metric mid-run invalidates all previous comparisons. The eval suite is the fixed reference; the skill is the variable.
8. **Log everything** — The TSV is your experiment journal. Even discarded changes teach you something. Append to `skillforge-results.tsv` after every iteration.

## Results Tracking

```tsv
iteration	commit	structure	triggers	quality	edges	efficiency	composability	total	status	description
0	a1b2c3d	72	58	65	40	80	70	64.2	baseline	initial state
1	b2c3d4e	72	65	65	40	80	70	65.3	keep	expand trigger description with edge phrases
2	-	72	62	65	40	80	70	64.8	discard	add negative trigger examples (too verbose)
```

## Improvement Strategies (Priority Order)

1. **Fix structural issues** — Missing frontmatter fields, no progressive disclosure
2. **Expand trigger description** — Add synonyms, edge phrases, negative boundaries
3. **Add examples** — Input/output pairs that demonstrate correct behavior
4. **Add edge-case handling** — What to do with malformed input, missing context
5. **Optimize token density** — Remove redundant instructions, compress verbose sections
6. **Add reference files** — Move deep content out of SKILL.md into references/
7. **Improve composability** — Add explicit handoff points for related skills

Read `references/skill-patterns.md` for common patterns and anti-patterns.

## Chaining with skill-creator

SkillForge and Anthropic's `skill-creator` are complementary:

- **skill-creator** builds v1 — captures intent, writes the draft, runs initial test cases with human review
- **SkillForge** grinds v1 to production — autonomous loop, mechanical metrics, overnight improvement

**Recommended workflow:**
1. `/skill-creator` → draft skill, run 2-3 test cases, get user feedback, iterate manually
2. User confirms "good enough to start grinding"
3. `/skillforge` → autonomous improvement with 30+ iterations, measurable scores
4. `/skillforge:report` → review what changed, confirm improvements
5. If new capabilities needed → back to `/skill-creator`

SkillForge will never create a new skill from scratch. If the user asks for that,
suggest using `skill-creator` first, then come back for autonomous improvement.

## Files in This Skill

```
skillforge/
├── SKILL.md                          ← You are here
├── references/
│   ├── improvement-protocol.md       ← 8-phase loop detail
│   ├── metrics-catalog.md            ← Scoring rubrics per dimension
│   └── skill-patterns.md             ← Patterns, anti-patterns, examples
├── scripts/
│   ├── analyze-skill.sh              ← Structural linting
│   └── score-skill.py                ← Quality scoring engine
└── templates/
    ├── eval-suite-template.json      ← Eval suite skeleton
    └── improvement-log-template.tsv  ← Results tracking template
```
