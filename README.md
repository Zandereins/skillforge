# SkillForge

**Autonomous skill improvement engine for Claude Code** — gradient descent for skill quality.

Set a goal, start the loop, let the agent grind through iterations while you review results.

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests: 51/51](https://img.shields.io/badge/Tests-51%2F51_passing-brightgreen)](skills/skillforge/scripts/test-integration.sh)
[![Composite: 99.3](https://img.shields.io/badge/Self--Score-99.3%2F100-blue)](skills/skillforge/scripts/score-skill.py)
[![Claude Code Skill](https://img.shields.io/badge/Claude_Code-Skill-8A2BE2)](https://docs.anthropic.com/en/docs/claude-code/skills)

---

## The Problem

You have a Claude Code skill. It kind of works. But:

- It doesn't trigger for the right prompts — false positives and false negatives
- Edge cases crash or produce garbage — no systematic testing
- It's bloated with instructions Claude already knows — wasted tokens
- You don't know what "good" looks like, let alone how to measure it

## The Solution

SkillForge applies [Karpathy's autoresearch pattern](https://github.com/karpathy/autoresearch) to **improving skills themselves**:

```
LOOP:
  1. Analyze current skill + eval results + history
  2. Pick ONE atomic improvement based on gap analysis
  3. Apply change, git commit
  4. Run eval suite → compute quality score
  5. Improved? Keep. Worse? git revert. Crash? Fix or skip.
  6. Log to history, repeat.
```

Every improvement stacks. Every failure auto-reverts. Progress is tracked with cost metrics.

## Demo

```
$ /skillforge
Target: .claude/skills/deploy/SKILL.md
Goal: Trigger accuracy from 60% to 90%

Baseline (#0): composite=62.5, triggers=60, structure=75
Exp 1: Add synonym expansion for deploy triggers → triggers=72 → Keep (+12)
Exp 2: Add negative boundary "NOT for local dev"   → triggers=80 → Keep (+8)
Exp 3: Compress verbose setup section              → triggers=78 → Discard (revert)
Exp 4: Add edge case for missing Dockerfile        → triggers=85 → Keep (+5)
Exp 5: Add "containerize" synonym                  → triggers=91 → Keep (+6)

Result: 62.5 → 91.3 composite in 5 iterations
Cost: 12,450 tokens estimated, 45s total duration
```

## Quick Start

### Prerequisites

- Python 3.9+
- Bash
- Git
- jq

### Install

```bash
git clone https://github.com/Zandereins/skillforge.git

# Project-local install
cp -r skillforge/skills/skillforge .claude/skills/skillforge
cp -r skillforge/commands/skillforge .claude/commands/skillforge

# Or global install
cp -r skillforge/skills/skillforge ~/.claude/skills/skillforge
cp -r skillforge/commands/skillforge ~/.claude/commands/skillforge
```

### First Run

```bash
# Analyze any skill
/skillforge:analyze
Target: .claude/skills/my-skill/SKILL.md

# Start autonomous improvement
/skillforge
Target: .claude/skills/my-skill/SKILL.md
Goal: Improve trigger accuracy to 90%+
Iterations: 30
```

### Verify Installation

```bash
cd skillforge/skills/skillforge
python3 scripts/score-skill.py SKILL.md --json    # Should output composite score
bash scripts/test-integration.sh                   # Should show 51/51 passing
```

## How It Works

### Quality Dimensions

SkillForge scores skills across 6 automated dimensions:

| Dimension | Weight | What It Measures | Method |
|-----------|--------|------------------|--------|
| **Structure** | 15% | Frontmatter, organization, progressive disclosure | Static analysis |
| **Trigger Accuracy** | 25% | Activates for right prompts, silent for wrong ones | TF-IDF eval suite |
| **Output Quality** | 25% | Following the skill produces correct results | Binary assertions |
| **Edge Coverage** | 15% | Handles unusual inputs gracefully | Edge case test suite |
| **Token Efficiency** | 10% | Information density, signal-to-noise ratio | Static analysis |
| **Composability** | 10% | Scope boundaries, handoff points, no conflicts | Static analysis |

Optional 7th dimension: **Clarity** (contradiction + ambiguity detection, `--clarity` flag).

### Cost Tracking

Every eval run logs real metrics to JSONL:

- `duration_ms` — actual wall-clock time per experiment
- `tokens_estimated` — estimated token count (words * 1.3)
- `delta` — composite score change from previous run
- `status` — `baseline`, `keep`, or `discard` (computed, not hardcoded)

Use `python3 scripts/progress.py results.jsonl --json --strategies` to analyze ROI across sessions.

### Cross-Session Learning

SkillForge reads improvement history at loop start:

1. Parse all previous keep/discard decisions with change types
2. Compute success rate per strategy (e.g., "synonym expansion: 80% keep rate")
3. Prioritize strategies with highest historical success rate
4. Detect plateaus: if last 5 iterations gained < 1 point, suggest stopping

## Commands

| Command | Purpose |
|---------|---------|
| `/skillforge` | Full autonomous improvement loop |
| `/skillforge:analyze` | Deep analysis with gap identification |
| `/skillforge:bench` | Establish quality baseline (iteration #0) |
| `/skillforge:eval` | Run evaluation suite |
| `/skillforge:report` | Generate improvement summary with diffs |

## Architecture

```
skillforge/
├── skills/skillforge/
│   ├── SKILL.md                     # Core skill definition (268 lines)
│   ├── eval-suite.json              # 25 assertions, triggers, edge cases
│   ├── references/
│   │   ├── improvement-protocol.md  # 9-phase autonomous loop spec
│   │   ├── metrics-catalog.md       # Scoring rubrics + custom metrics
│   │   └── skill-patterns.md        # Patterns and anti-patterns
│   ├── scripts/
│   │   ├── score-skill.py           # 6-dimension scorer (--diff, --clarity)
│   │   ├── run-eval.sh              # Unified eval runner with cost tracking
│   │   ├── progress.py              # Progress analysis + ASCII charts
│   │   ├── runtime-evaluator.py     # Live Claude invocation testing
│   │   ├── analyze-skill.sh         # Structural linter (100-point scale)
│   │   ├── test-integration.sh      # 51 integration tests
│   │   └── test-self.sh             # 12 self-scoring tests
│   ├── templates/
│   │   ├── eval-suite-template.json
│   │   └── improvement-log-template.jsonl
│   └── history/                     # Experiment diffs + results
├── commands/skillforge/             # Slash command definitions
│   ├── init.md
│   ├── analyze.md
│   ├── bench.md
│   ├── eval.md
│   └── report.md
├── .claude-plugin/
│   ├── plugin.json
│   └── marketplace.json
├── CHANGELOG.md
├── CONTRIBUTING.md
├── SECURITY.md
└── LICENSE
```

## Real-World Results

### Self-Improvement

SkillForge scores itself. Current results:

| Metric | Value |
|--------|-------|
| Composite Score | **99.3 / 100** |
| Structure | 100 |
| Trigger Accuracy | 100 |
| Output Quality | 100 |
| Edge Coverage | 100 |
| Efficiency | 93 |
| Composability | 100 |
| Binary Assertions | **25/25 passing** |
| Integration Tests | **51/51 passing** |
| Self-Tests | **12/12 passing** |

The journey from v1.0 (62.5) to v3.1 (99.3) took 20 experiments across 4 major versions.

## Design Principles

Based on [Karpathy's autoresearch](https://github.com/karpathy/autoresearch):

1. **Constraint = Enabler** — Bounded scope, fixed metrics, atomic changes
2. **Mechanical Verification** — If you can't score it with a script, you can't improve it autonomously
3. **One Change Per Iteration** — Atomic edits isolate causation
4. **Automatic Rollback** — Failed changes revert via `git revert`
5. **Git as Memory** — Every kept change committed, agent reads history to learn patterns
6. **Human Sets Goal, Agent Executes** — Clear separation of strategy and tactics

## Chaining with skill-creator

SkillForge and Anthropic's `skill-creator` are complementary:

- **skill-creator** builds v1 — captures intent, writes the draft
- **SkillForge** grinds v1 to production — autonomous loop, mechanical metrics

**Recommended workflow:** `skill-creator` → build v1 → `skillforge` → grind to 90%+ → ship

## Inspiration & Credits

- **[Andrej Karpathy](https://github.com/karpathy)** — [autoresearch](https://github.com/karpathy/autoresearch): the original autonomous experiment loop
- **[Udit Goenka](https://github.com/uditgoenka)** — [autoresearch](https://github.com/uditgoenka/autoresearch): generalized autoresearch for Claude Code
- **[Anthropic](https://anthropic.com)** — [Claude Code](https://docs.anthropic.com/en/docs/claude-code) skills system

## Contributing

Contributions welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT — see [LICENSE](LICENSE).
