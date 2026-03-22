# SkillForge

Your Claude Code skills, automatically better.

> Trigger accuracy 63% → 89%. Efficiency 45 → 83. Structure 72 → 90. One command. Zero manual work.

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests: 99/99](https://img.shields.io/badge/Tests-99%2F99_passing-brightgreen)](skills/skillforge/scripts/test-integration.sh)
[![Structural Score: 99.9](https://img.shields.io/badge/Structural_Score-99.9%2F100-blue)](skills/skillforge/scripts/score-skill.py)
[![v5.1](https://img.shields.io/badge/Version-5.1-F59E0B)](CHANGELOG.md)
[![Claude Code Skill](https://img.shields.io/badge/Claude_Code-Skill-8A2BE2)](https://docs.anthropic.com/en/docs/claude-code/skills)

---

## Demo

### Init — Auto-discovers SKILL.md, scores baseline with grade badges

```
SkillForge Init: skillforge
================================

Generated eval-suite.json:
  Triggers:    8 positive + 5 negative + 3 edge = 16 total
  Test cases:  3 (7 assertions)
  Edge cases:  2 (2 assertions)

Baseline Score: 100/100  [S]

  structure       ██████████  100/100
  triggers        ██████████  100/100
  quality         ██████████  100/100
  edges           ██████████  100/100
  efficiency      █████████░  93/100
  composability   ██████████  100/100
  runtime                     n/a

Strong baseline! Run /skillforge:auto for final polish.
```

### Dashboard — Colored gauges, grade badges, achievements

```
======================================================================
  SkillForge Health Dashboard: skillforge
======================================================================

  Structural Score: ████████████████████  99.0/100  [S]
    [7/8 dimensions, 91% coverage]

  Dimensions:
    structure       ██████████  100/100
    triggers        ██████████  95/100
    quality         ██████████  100/100
    edges           ██████████  100/100
    efficiency      █████████░  93/100
    composability   ██████████  100/100
    clarity         ██████████  100/100

  Top 1 Improvements:
  ------------------------------------------------------------
    #1 [triggers] false_positives:2
       Add 'Do NOT use for...' boundaries to exclude false-positive scenarios
       delta: +3.5  |  priority: 0.42

  Achievements: ████░░░░░░  4/10
  ⚡ 🎯 💎 🟢

======================================================================
```

### Doctor — Scan ALL installed skills at once

```
======================================================================
  SkillForge Doctor — Skill Health Check
======================================================================

  1 skills scanned | 1 healthy | 4 mesh issues

  Skill                      Score  Grade   Dims  Issues  Action
  --------------------------------------------------------------------
  skillforge                   99    [S]    6/7       1  Healthy — consider runtime eval

  Mesh Health: 68/100 (4 cross-skill issues)
  Run /skillforge:mesh for details.

  NOTE: Scores are STRUCTURAL — they measure file organization,
  not runtime effectiveness. Use --runtime for validated scoring.

======================================================================
```

### Auto-Improve — Autonomous loop with EMA-based stopping

```
Scoring baseline...
Baseline: 98.9/100 (6 dims)

--- Iteration 1 ---
Stopping: composite >= 98 (98.9)

  SkillForge Auto-Improve Complete
  ──────────────────────────────────────────────────
  Score:  99 → 99/100  ████████████████████  (+0.0)  [S]
  Iters:  0  |  Kept: 0  |  Time: 0s
  Stop:   composite >= 98 (98.9)
```

---

## Quick Start

```bash
# Install (one command)
git clone https://github.com/Zandereins/skillforge.git && bash skillforge/install.sh

# Verify — see the health of all your installed skills
/skillforge:doctor

# Try it — run on the included demo skill
/skillforge:init demo/bad-skill/SKILL.md

# Improve any skill — autonomous, walk away
/skillforge:auto

# Share — get your badge
/skillforge:report
```

**Prerequisites:** Python 3.9+, Bash, Git, jq — the installer checks all of these.

---

## What Happens

| Step | You Do | SkillForge Does |
|------|--------|-----------------|
| **Doctor** | Run one command | See health grades for ALL your installed skills |
| **Init** | Point at a SKILL.md | Auto-discovers file, generates eval suite, scores baseline with grade badge |
| **Improve** | Walk away | Applies fixes, reverts regressions, stops when ROI drops |
| **Report** | Share the markdown | Before/after table, heatmap, achievements, recommendations |

---

## Before → After

```
Baseline:  ██████░░░░░░░░░░░░░░  62.5/100  [C]
After 18x: ████████████████████  99.9/100  [S]  (+37 points, zero human input)
```

What actually changed in a real run:

- **Trigger Accuracy** 63% → 89% — added deployment-related synonyms
- **Efficiency** 45 → 83 — removed 312 words of hedging language
- **Structure** 72 → 90 — added 6 examples from real use cases

The loop applies patches, checks the score, and keeps or reverts each one. When three consecutive windows show diminishing returns, it stops.

---

## How It Works

1. **Score** — 7 dimensions (structure, triggers, quality, edges, efficiency, composability, clarity)
2. **Gradient** — Identifies highest-impact fixes with predicted score delta
3. **Apply** — Patches SKILL.md deterministically, re-scores, keeps or reverts
4. **Learn** — Remembers which strategies worked across sessions via TF-IDF episodic memory

60–70% of all fixes are fully deterministic — frontmatter insertions, noise removal, TODO cleanup — and require no LLM at all. The loop runs unattended.

---

## Commands

| Command | What It Does |
|---------|--------------|
| `/skillforge` | Full autonomous loop with GOAL + METRIC |
| `/skillforge:doctor` | Scan ALL installed skills, show health summary |
| `/skillforge:auto` | Self-driving auto-improve (deterministic patches, no prompts) |
| `/skillforge:init` | Bootstrap eval suite + baseline from any SKILL.md |
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

## Scoring Dimensions

| Dimension | Weight | Grade | What It Measures | What It Does NOT Measure |
|-----------|--------|-------|-----------------|-------------------------|
| Structure | 15% | S/A/B/C/D/F | Frontmatter, headers, examples, progressive disclosure | Whether instructions are correct |
| Trigger Accuracy | 20% | S/A/B/C/D/F | TF-IDF keyword overlap against eval suite prompts | Actual Claude triggering behavior |
| Eval Coverage | 20% | S/A/B/C/D/F | Assertion breadth and eval suite coverage | Whether output is actually correct |
| Edge Coverage | 15% | S/A/B/C/D/F | Edge case definitions in eval suite | Whether edges are handled at runtime |
| Token Efficiency | 10% | S/A/B/C/D/F | Information density, signal-to-noise ratio | Whether content is useful to Claude |
| Composability | 5% | S/A/B/C/D/F | Scope boundaries, handoff declarations | Whether skills work together |
| Clarity | *(bonus)* | S/A/B/C/D/F | Contradictions, ambiguity, vague references | Whether instructions are clear to Claude |
| Runtime *(opt-in)* | 15% | S/A/B/C/D/F | **Actual Claude behavior** against assertions | — |

Grades: **S** (>=95), **A** (>=85), **B** (>=75), **C** (>=65), **D** (>=50), **F** (<50).

> **Important:** The default composite score is a **structural lint score** — it measures
> file organization and keyword coverage, not whether the skill actually works. A 99/100
> skill with perfect structure can still fail at runtime. Enable `--runtime` or run
> `/skillforge:eval` with runtime assertions for validated scoring.

Weights auto-calibrate from runtime data when available. Override with `--weights "triggers=0.4,structure=0.3"`.

---

## v5.1 Features (Latest)

**Atomic Writes** — `.tmp` + `rename()` pattern prevents skill file corruption on crash.

**Deterministic LSH** — `hashlib.sha256` replaces `hash()` for reproducible mesh results across runs.

**Honest Scoring** — "Structural Score" everywhere instead of misleading "Quality Score". Transparent about what the number means.

**Stemming Tokenizer** — Suffix-stripping replaces fixed synonym tables. Better keyword matching with zero maintenance.

**Beam Search** — Top-3 exploration instead of greedy top-1 from iteration 4 onward. Finds better improvement paths.

**EMA Plateau Detection** — Exponential Moving Average replaces fixed-window ROI. Smoother, more reliable stopping.

**MinHash + LSH** — O(n) mesh analysis instead of O(n^2) for 50+ skills. Scales to large skill collections.

**Context-aware Patches** — Generates meaningful descriptions instead of TODOs. Patches that actually help.

**Doctor Command** — `skillforge doctor` scans ALL installed skills in one pass. Shows health summary with grades.

**Dimension Guard** — Prevents patches that tank a single dimension by >15 points. No more trading one strength for another.

**Coherence Check** — Instruction-assertion alignment as a quality bonus. Catches disconnects between what a skill says and what it tests.

**40+ Pre-compiled Regex** — Performance optimization across the scorer. Faster scoring on large skills.

**Public Cache API** — `invalidate_cache()` replaces direct `_file_cache.pop()`. Clean interface for cache management.

## v5.0 Features

**Auto-Apply** — Deterministic patches apply without an LLM. Frontmatter, noise, TODOs — fixed directly.

**Grade System** — Letter grades [S/A/B/C/D/F] on every dimension and composite score. Color-coded in terminal output.

**Dimension Heatmap** — ASCII heatmap across iterations in reports. Shows which dimensions improved when.

**Achievements** — Unlockable badges for hitting milestones. Tracked per-skill, shown in dashboard and reports.

**Init Auto-Discovery** — `init-skill.py` finds SKILL.md automatically, shows colored dimension bars and contextual next steps.

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
| Structural Score | **99.9 / 100** [S] *(structural only — see note below)* |
| Binary assertions | **25/25 passing** |
| Integration tests | **87/87 passing** |
| Self-tests | **12/12 passing** |
| Total tests | **99/99 passing** |
| Journey | v1.0 (62.5) → v5.1 (99.9) across 5 major versions |
| Code review | **3 CRITICAL + 9 HIGH fixed** in v5.1.1 |

> The 99.9 score means "near-perfect structure" — not "perfect skill". Runtime
> validation (`--runtime`) tests actual Claude behavior and is the true quality gate.

27 security fixes + 12 code review fixes from multi-agent audits. It practices what it preaches.

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
│   ├── dashboard.py            # Unified health dashboard with gauges
│   ├── generate-report.py      # Shareable markdown report + heatmap
│   ├── init-skill.py           # Eval-suite bootstrapper with auto-discovery
│   ├── terminal_art.py         # Shared render library (grades, heatmap, bars)
│   ├── achievements.py         # Achievement tracker (10 unlockable badges)
│   ├── skill-mesh.py           # Multi-skill conflict detection + fixes
│   ├── meta-report.py          # Strategy predictor + calibration
│   ├── episodic-store.py       # Cross-session TF-IDF memory
│   ├── doctor.py               # Health check for all installed skills
│   ├── parallel-runner.py      # Git worktree parallel experiments
│   ├── score_skill.py          # Underscore alias (Python import compat)
│   ├── text_gradient.py        # Underscore alias
│   ├── skill_mesh.py           # Underscore alias
│   ├── parallel_runner.py      # Underscore alias
│   ├── run-eval.sh             # Binary assertion engine
│   ├── progress.py             # Convergence analysis
│   ├── runtime-evaluator.py    # Live Claude invocation testing
│   ├── test-integration.sh     # 87 integration tests
│   └── test-self.sh            # 12 self-tests (dogfooding)
├── hooks/
│   └── session-injector.js     # Surfaces failures at session start
└── templates/
    └── eval-suite-template.json
```

All file writes use atomic tmp+rename. All regex on user data is guarded against `re.error`.
All JSON reads specify `encoding="utf-8"` explicitly.

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

## Badge

Score your skill and add this badge to your README:

```markdown
[![SkillForge: 99.9 [S]](https://img.shields.io/badge/SkillForge-99.9%2F100_%5BS%5D-brightgreen)](https://github.com/Zandereins/skillforge)
```

[![SkillForge: 99.9 [S]](https://img.shields.io/badge/SkillForge-99.9%2F100_%5BS%5D-brightgreen)](https://github.com/Zandereins/skillforge)

---

*Built by [Franz Paul](https://github.com/Zandereins) with Claude Code.*
