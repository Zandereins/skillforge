# SkillForge

Your Claude Code skills, automatically better.

> 62.5 → 99.9 points. One command. Zero manual work.

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests: 51/51](https://img.shields.io/badge/Tests-51%2F51_passing-brightgreen)](skills/skillforge/scripts/test-integration.sh)
[![Score: 99.9](https://img.shields.io/badge/Structural_Score-99.9%2F100-blue)](skills/skillforge/scripts/score-skill.py)
[![v5.0](https://img.shields.io/badge/Version-5.0-F59E0B)](CHANGELOG.md)
[![Claude Code Skill](https://img.shields.io/badge/Claude_Code-Skill-8A2BE2)](https://docs.anthropic.com/en/docs/claude-code/skills)

---

## 60-Second Quick Start

```bash
# 1. Install (global — works across all projects)
git clone https://github.com/Zandereins/skillforge.git
cp -r skillforge/skills/skillforge ~/.claude/skills/
cp -r skillforge/commands/skillforge ~/.claude/commands/

# 2. Init — point at any SKILL.md, get baseline + eval suite
/skillforge:init

# 3. Improve — autonomous, walk away
/skillforge:auto

# 4. Report — shareable before/after results
/skillforge:report
```

**Prerequisites:** Python 3.9+, Bash, Git, jq

---

## What Happens

| Step | You Do | SkillForge Does |
|------|--------|-----------------|
| **Init** | Point at a SKILL.md | Generates eval suite, scores baseline across 6 dimensions |
| **Improve** | Walk away | Applies fixes, reverts regressions, stops when ROI drops |
| **Report** | Share the markdown | Before/after table, strategy analysis, recommendations |

---

## Before → After

```
Baseline:  ██████░░░░░░░░░░░░░░  62.5/100
After 18x: ████████████████████  99.9/100  (+37 points, zero human input)
```

What actually changed in a real run:

- **Trigger Accuracy** 63% → 89% — added deployment-related synonyms
- **Efficiency** 45 → 83 — removed 312 words of hedging language
- **Structure** 72 → 90 — added 6 examples from real use cases

The loop applies patches, checks the score, and keeps or reverts each one. When three consecutive windows show diminishing returns, it stops.

---

## How It Works

1. **Score** — 6 dimensions (structure, triggers, quality, edges, efficiency, composability)
2. **Gradient** — Identifies highest-impact fixes with predicted score delta
3. **Apply** — Patches SKILL.md deterministically, re-scores, keeps or reverts
4. **Learn** — Remembers which strategies worked across sessions via TF-IDF episodic memory

60–70% of all fixes are fully deterministic — frontmatter insertions, noise removal, TODO cleanup — and require no LLM at all. The loop runs unattended.

---

## Commands

| Command | What It Does |
|---------|--------------|
| `/skillforge` | Full autonomous loop with GOAL + METRIC |
| `/skillforge:auto` | Self-driving auto-improve (deterministic patches, no prompts) |
| `/skillforge:analyze` | One-shot gap analysis with ranked recommendations |
| `/skillforge:bench` | Establish quality baseline for a skill |
| `/skillforge:eval` | Run eval suite assertions |
| `/skillforge:report` | Generate shareable markdown report with diffs |
| `/skillforge:mesh` | Detect trigger conflicts across all installed skills |
| `/skillforge:mesh-evolve` | Conflicts + auto-generated fix actions |
| `/skillforge:triage` | Cluster failures, auto-generate fixes |
| `/skillforge:predict` | Best strategy from cross-session data |
| `/skillforge:recall` | Search episodic memory for relevant past learnings |
| `/skillforge:log-failure` | Log a skill failure for later triage |

---

## Quality Dimensions

| Dimension | Weight | What It Measures |
|-----------|--------|-----------------|
| Structure | 15% | Frontmatter, headers, examples, progressive disclosure |
| Trigger Accuracy | 20% | TF-IDF keyword overlap against eval suite prompts |
| Output Quality | 20% | Assertion breadth and eval suite coverage |
| Edge Coverage | 15% | Edge case definitions and handling |
| Token Efficiency | 10% | Information density, signal-to-noise ratio |
| Composability | 5% | Scope boundaries, handoff declarations |
| Runtime *(opt-in)* | 15% | Actual Claude behavior against assertions |

Weights auto-calibrate from runtime data when available. Override with `--weights "triggers=0.4,structure=0.3"`.

---

## v5.0 Features

**Auto-Apply** — Deterministic patches apply without an LLM. Frontmatter, noise, TODOs — fixed directly.

**Strategy Predictor** — Learns which approaches work before trying them. Groups history by `(domain, strategy_type, gap_bucket)` and computes success probability.

**Episodic Memory** — TF-IDF semantic search across all past improvement sessions. Size-capped with automatic consolidation.

**Parallel Branching** — When stuck (5+ discards in a row), spins up 3 strategies via git worktrees and keeps the best result.

**Mesh Analysis** — Scans all installed skills for trigger overlaps and scope collisions. Generates fix actions, not just a report.

**ROI Stopping** — Automatically stops when marginal improvement drops below threshold for 3 consecutive windows. No babysitting required.

---

## Self-Score

SkillForge scores itself. Dogfooding, not marketing.

| Metric | Value |
|--------|-------|
| Structural Score | **99.9 / 100** |
| Binary assertions | **25/25 passing** |
| Integration tests | **51/51 passing** |
| Journey | v1.0 (62.5) → v5.0 (99.9) across 5 major versions |

27 security fixes applied from a 15-agent deep audit. It practices what it preaches.

---

## Architecture

```
skills/skillforge/
├── SKILL.md                    # Skill definition (what Claude reads)
├── eval-suite.json             # 25+ triggers, assertions, edge cases
├── scripts/
│   ├── auto-improve.py         # Autonomous improvement loop
│   ├── score-skill.py          # 7-dimension scorer + auto-weights
│   ├── text-gradient.py        # Fix identification + auto-apply
│   ├── skill-mesh.py           # Multi-skill conflict detection + fixes
│   ├── meta-report.py          # Strategy predictor + calibration
│   ├── episodic-store.py       # Cross-session TF-IDF memory
│   ├── parallel-runner.py      # Git worktree parallel experiments
│   ├── run-eval.sh             # Binary assertion engine
│   ├── progress.py             # Convergence analysis
│   ├── runtime-evaluator.py    # Live Claude invocation testing
│   └── test-integration.sh     # 51 integration tests
├── hooks/
│   └── session-injector.js     # Surfaces failures at session start
└── templates/
    └── eval-suite-template.json
```

---

## Ecosystem

`skill-creator` builds a v1 skill. SkillForge grinds it to production quality.

```
skill-creator → v1 SKILL.md → /skillforge:auto → autonomous grinding → ship
```

- **[skill-creator](https://github.com/anthropics/courses/tree/master/claude-code/09-skill-creator)** — generate the first draft
- **[autoresearch](https://github.com/uditgoenka/autoresearch)** — generalized autonomous research for Claude Code

---

## License

MIT — do whatever you want.

---

*Built by [Franz Paul](https://github.com/Zandereins) with Claude Code.*
