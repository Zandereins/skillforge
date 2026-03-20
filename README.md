# SkillForge

**The self-evolving skill engine for Claude Code.**

Your 50th skill ships in half the iterations of your 1st. Every failure teaches the system. Every success compounds.

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests: 51/51](https://img.shields.io/badge/Tests-51%2F51_passing-brightgreen)](skills/skillforge/scripts/test-integration.sh)
[![Score: 99.4](https://img.shields.io/badge/Structural_Score-99.4%2F100-blue)](skills/skillforge/scripts/score-skill.py)
[![v4.0](https://img.shields.io/badge/Version-4.0-F59E0B)](CHANGELOG.md)
[![Claude Code Skill](https://img.shields.io/badge/Claude_Code-Skill-8A2BE2)](https://docs.anthropic.com/en/docs/claude-code/skills)

---

## Why SkillForge

| What exists today | What SkillForge does |
|:---|:---|
| Manual skill editing by feel | **Text gradients** — scored, ranked, directed fixes with predicted impact |
| Skills as isolated files | **Skill mesh** — multi-skill health monitoring across your entire skill library |
| Blind iteration (guess, check, revert) | **Meta-learning** — data-informed strategy selection that improves over time |
| Failures vanish when session ends | **Failure triage** — failures become eval cases automatically |
| One-shot optimization | **Compounding loop** — each skill optimized makes the next one easier |

---

## The Loop

```
LOOP (autonomous, never pauses):
  1. Analyze skill + scores + history + text gradients
  2. Pick ONE atomic fix (highest priority gradient first)
  3. Apply change, git commit
  4. Run eval suite, compute quality score
  5. Improved? Keep. Worse? git revert.
  6. Log to meta-learning store, repeat.

Every kept change builds on the last. Every discard informs the next attempt.
```

Based on [Karpathy's autoresearch](https://github.com/karpathy/autoresearch) pattern — adapted for text artifacts instead of hyperparameters.

---

## Demo

```
$ /skillforge
Target: .claude/skills/deploy/SKILL.md
Goal: Trigger accuracy from 60% to 90%

Text gradients found 8 improvements (top 3):
  #1 [triggers] Add keywords: deploy, release, ship        delta: ~4.0  effort: simple
  #2 [triggers] Add negative boundary for local dev         delta: ~3.0  effort: simple
  #3 [composability] Add scope boundaries                   delta: +2.0  effort: simple

Exp 1: Apply gradient #1 → triggers=72 → Keep (+12)
Exp 2: Apply gradient #2 → triggers=80 → Keep (+8)
Exp 3: Compress verbose setup section → triggers=78 → Discard (revert)
Exp 4: Add edge case for missing Dockerfile → triggers=85 → Keep (+5)
Exp 5: Add "containerize" synonym → triggers=91 → Keep (+6)

Result: 62.5 → 91.3 composite in 5 iterations
```

---

## Quick Start

**Prerequisites:** Python 3.9+, Bash, Git, jq

```bash
git clone https://github.com/Zandereins/skillforge.git

# Install (project-local)
cp -r skillforge/skills/skillforge .claude/skills/skillforge
cp -r skillforge/commands/skillforge .claude/commands/skillforge

# Verify
cd skillforge/skills/skillforge
python3 scripts/score-skill.py SKILL.md --json         # Score any skill
python3 scripts/text-gradient.py SKILL.md --top 5       # See what to fix
python3 scripts/skill-mesh.py --json                    # Scan for conflicts
bash scripts/test-integration.sh                         # 51/51 passing
```

Then in Claude Code:
```
/skillforge:analyze                    # What's wrong with my skill?
/skillforge                            # Start autonomous improvement loop
/skillforge:mesh                       # Check all skills for conflicts
```

---

## v4.0 — The Self-Evolving Engine

### Text Gradients

Inverts scorer diagnostics into a **prioritized fix list** with estimated impact. No more guessing what to change.

```bash
$ python3 scripts/text-gradient.py my-skill/SKILL.md --json --top 3

#1  [structure] no_frontmatter
    Add YAML frontmatter: ---\nname: ...\ndescription: ...\n---
    delta: +6.0  |  effort: simple  |  priority: 6.0

#2  [composability] no_scope_boundaries
    Add 'Use this skill when...' AND 'Do NOT use for...' sections
    delta: +2.0  |  effort: simple  |  priority: 2.0
```

The autonomous loop reads gradients first (Phase 2: IDEATE) — directed improvement replaces trial-and-error.

### Skill Mesh

Scans **all installed skills** for trigger overlap, broken handoffs, and scope collisions.

```bash
$ python3 scripts/skill-mesh.py --json

Mesh Health: 72/100
[CRITICAL] Trigger overlap: deploy <-> release (87% similarity)
[WARNING]  Broken handoff: testing references 'lint-master' — not found
[INFO]     Scope collision: api-design <-> backend (domain: backend)
```

Uses TF-IDF cosine similarity across skill descriptions. Thresholds: critical (>=0.70), warning (0.45-0.69), info (0.20-0.44).

### Meta-Learning

Every eval emits data to `~/.skillforge/meta/`. Over time, SkillForge learns which strategies work:

```bash
$ python3 scripts/meta-report.py

[1] Static Score <-> Runtime Correlation
  triggers:     r=+0.72 — strong positive, consider increasing weight
  structure:    r=+0.31 — weak correlation
  Suggested: --weights "triggers=0.40,structure=0.20,..."

[2] Strategy Effectiveness
  trigger_expansion    keep=80%  avg_delta=+2.1  (8/10)
  noise_reduction      keep=60%  avg_delta=+0.8  (3/5)
  example_addition     keep=40%  avg_delta=+1.2  (2/5)
```

Data informs decisions. Weights stay under user control via `--weights`.

### Failure Log & Triage

Eval failures **auto-log** to `.skillforge/failures.jsonl`. A SessionStart hook surfaces untriaged failures when you start a new session. Triage clusters them and proposes fixes:

```
/skillforge:triage
Found 7 untriaged failures across 2 skills:
  Cluster 1: deploy / assertion_failed (4 failures)
    Fix: Add Dockerfile handling + deploy steps section
  Cluster 2: testing / runtime_timeout (3 failures)
    Fix: Simplify edge case handling
```

---

## Quality Dimensions

6 structural dimensions (weights configurable via `--weights`), optional 7th (clarity):

| Dimension | Weight | Measures | Limitation |
|:---|:---:|:---|:---|
| **Structure** | 15% | Frontmatter, organization, progressive disclosure | Cannot assess instruction correctness |
| **Trigger Accuracy** | 25% | Keyword overlap with eval prompts (TF-IDF) | Does not predict actual Claude triggering |
| **Output Quality** | 25% | Eval suite coverage and assertion breadth | Does not verify runtime output quality |
| **Edge Coverage** | 15% | Edge case definitions in eval suite | Does not verify handling at runtime |
| **Token Efficiency** | 10% | Information density, signal-to-noise ratio | Cannot assess content usefulness |
| **Composability** | 10% | Scope boundaries, handoff points | Cannot verify multi-skill interaction |

**Important:** These measure structural quality — how well-formed your skill file is. They do NOT measure runtime effectiveness. Use `--runtime` for behavioral validation.

---

## Commands

| Command | Purpose |
|:---|:---|
| `/skillforge` | Full autonomous improvement loop |
| `/skillforge:analyze` | Deep analysis with gap identification |
| `/skillforge:bench` | Establish quality baseline |
| `/skillforge:eval` | Run evaluation suite |
| `/skillforge:report` | Generate improvement summary with diffs |
| `/skillforge:mesh` | Scan all skills for conflicts and overlaps |
| `/skillforge:triage` | Cluster failures, auto-generate fixes |
| `/skillforge:log-failure` | Manually log a skill failure |

---

## Architecture

```
skillforge/
├── skills/skillforge/
│   ├── SKILL.md                      # Core skill definition
│   ├── eval-suite.json               # 25 assertions, triggers, edge cases
│   ├── scripts/
│   │   ├── score-skill.py            # 6-dimension scorer
│   │   ├── text-gradient.py          # Scorer inversion → fix list
│   │   ├── skill-mesh.py             # Multi-skill conflict detection
│   │   ├── meta-report.py            # Data-informed insights
│   │   ├── run-eval.sh               # Eval runner + meta emission + failure logging
│   │   ├── progress.py               # Convergence charts + strategy analysis
│   │   ├── runtime-evaluator.py      # Live Claude invocation testing
│   │   └── test-integration.sh       # 51 integration tests
│   ├── hooks/
│   │   ├── hooks.json                # SessionStart hook registration
│   │   └── session-injector.js       # Surfaces untriaged failures
│   ├── references/                   # Improvement protocol, metrics catalog, patterns
│   └── templates/                    # Eval suite + log templates
├── commands/skillforge/              # 8 slash commands
└── .claude-plugin/                   # Plugin manifest
```

---

## Self-Score

SkillForge scores itself — dogfooding the tool it builds.

| Metric | Value |
|:---|:---|
| Structural Score | **99.4 / 100** |
| All 6 dimensions | 93-100 each |
| Binary assertions | **25/25 passing** |
| Integration tests | **51/51 passing** |
| Journey | v1.0 (62.5) → v4.0 (99.4) across 4 major versions |

This is a **structural lint score**, not a quality oracle. Runtime effectiveness requires `--runtime` evaluation.

---

## Design Principles

1. **Measurement before improvement** — You cannot improve what you cannot measure
2. **Mechanical verification** — If you can't score it with a script, you can't improve it systematically
3. **Atomic changes** — One edit per iteration isolates causation
4. **Automatic rollback** — Failed changes revert via `git revert`
5. **Git as memory** — Every kept change committed, history informs future strategy
6. **Discipline is the product** — The loop enforces what humans skip

### Honest Limitations

- Static analysis has fundamental limits — `grep` against content does not equal "skill works"
- TF-IDF does not predict Claude triggering — it measures keyword overlap, not semantic matching
- Text changes are not atomic — one phrase change affects multiple dimensions
- The composite score is a lint score, not a quality oracle

---

## Ecosystem

**Complementary tools:**
- **[skill-creator](https://github.com/anthropics/courses/tree/master/claude-code/09-skill-creator)** builds v1 → **SkillForge** grinds v1 to production
- **[autoresearch](https://github.com/karpathy/autoresearch)** (Karpathy) — the original autonomous experiment loop
- **[autoresearch](https://github.com/uditgoenka/autoresearch)** (Goenka) — generalized autoresearch for Claude Code

**Workflow:** `skill-creator` → build v1 → `/skillforge` → grind to 90%+ → ship

---

## Contributing

Contributions welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT — see [LICENSE](LICENSE).
