# SkillForge

Stop manually auditing your Claude Code skills.

> You wrote a skill. It worked. Three weeks later, triggers misfire, edge cases slip through, instructions contradict themselves. SkillForge fixes all of it autonomously — deterministic patches, mechanical scoring, zero hallucinations on the rule-based fixes.

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests: 99/99](https://img.shields.io/badge/Tests-99%2F99_passing-brightgreen)](skills/skillforge/scripts/test-integration.sh)
[![Structural Score: 99.9](https://img.shields.io/badge/Structural_Score-99.9%2F100-blue)](skills/skillforge/scripts/score-skill.py)
[![v5.1.1](https://img.shields.io/badge/Version-5.1.1-F59E0B)](CHANGELOG.md)
[![Claude Code Skill](https://img.shields.io/badge/Claude_Code-Skill-8A2BE2)](https://docs.anthropic.com/en/docs/claude-code/skills)

---

## See It Work

**A real skill going from [D] to [S] — zero human input:**

<p align="center">
  <img src="demo/skillforge-demo.gif" alt="SkillForge improving a skill from 56.9 to 99.9" width="720">
</p>

```
Baseline:  ██████░░░░░░░░░░░░░░  56.9/100  [D]
After 18x: ████████████████████  99.9/100  [S]

What changed:
  Trigger accuracy   0% → 89%    Added keyword matching + negative boundaries
  Structure         75 → 100     Added examples, edge cases, frontmatter
  Efficiency        35 → 93      Removed hedging language, improved density
  Composability     40 → 100     Added scope boundaries + handoff declarations
```

Unlike code linters, SkillForge improves skills via multi-dimensional eval suites, automatic patch generation, and cross-session learning.

<details>
<summary><b>Dashboard</b> — Health overview for any skill</summary>

```
======================================================================
  SkillForge Health Dashboard: skillforge
======================================================================

  Structural Score: ████████████████████  99.9/100  [S]
    [7/8 dimensions, 91% coverage]

  Dimensions:
    structure       ██████████  100/100
    triggers        ██████████  100/100
    quality         ██████████  100/100
    edges           ██████████  100/100
    efficiency      █████████░  93/100
    composability   ██████████  100/100
    clarity         ██████████  100/100
======================================================================
```
</details>

<details>
<summary><b>Auto-Improve</b> — Autonomous grinding with EMA-based stopping</summary>

```
Scoring baseline...
Baseline: 99.9/100 (6 dims)

--- Iteration 1 ---
Stopping: composite >= 98 (99.9)

  SkillForge Auto-Improve Complete
  ──────────────────────────────────────────────────
  Score:  100 → 100/100  ████████████████████  (+0.0)  [S]
  Iters:  0  |  Kept: 0  |  Time: 0s
  Stop:   composite >= 98 (99.9)
  (dry run — no changes written)
```
</details>

<details>
<summary><b>Doctor</b> — Scan all installed skills at once</summary>

```
======================================================================
  SkillForge Doctor — Skill Health Check
======================================================================

  1 skills scanned | 1 healthy | 4 mesh issues

  Skill                      Score  Grade   Dims  Issues  Action
  --------------------------------------------------------------------
  skillforge                  100    [S]    6/7       0  Healthy

  Mesh Health: 68/100 (4 cross-skill issues)
  Run /skillforge:mesh for details.

  NOTE: Scores are STRUCTURAL — they measure file organization,
  not runtime effectiveness. Use --runtime for validated scoring.
======================================================================
```
</details>

---

## Try It

> **Note:** SkillForge commands (`/skillforge:*`) run inside [Claude Code](https://docs.anthropic.com/en/docs/claude-code), not in a regular terminal.

```bash
# 1. Install (in your regular terminal)
git clone https://github.com/Zandereins/skillforge.git && bash skillforge/install.sh

# 2. Score the included demo skill (in Claude Code)
/skillforge:init demo/bad-skill/SKILL.md

# 3. Watch it improve autonomously (in Claude Code)
/skillforge:auto
```

**What you'll see:** The score climbs from 56 [D] through [C], [B], [A] to [S] as SkillForge applies patches, checks each delta, and reverts anything that regresses. When ROI drops below threshold, it stops.

**Prerequisites:** Python 3.9+, Bash, Git, jq — the installer checks all of these.

Already have skills? Run `/skillforge:doctor` to see health grades for all your installed skills at once.

---

## This Is For You If

- **Skill Creator** — Run `/skillforge:init` on your v1 skill to get a baseline + eval suite
- **Skill Maintainer** — Run `/skillforge:auto` to grind any skill from [C] to [S] overnight
- **Fleet Manager (10+ skills)** — Run `/skillforge:doctor` to scan everything, detect conflicts
- **Quality Gate** — Run `/skillforge:eval` before shipping to validate assertions pass

---

## Why It Works

**Autonomous** — Runs unattended. Applies patches, measures delta, reverts regressions, stops when ROI drops. No prompts, no babysitting.

**Deterministic** — 60-70% of fixes are rule-based: frontmatter insertion, noise removal, TODO cleanup. No LLM needed. Same input, same output.

**Empirical** — 6 scoring dimensions (structure, triggers, quality, edges, efficiency, composability) + optional runtime validation against actual Claude behavior.

**Learns** — Episodic memory remembers which strategies worked across sessions. Predicts success before trying. Your 50th skill improves faster than your 1st.

**Scales** — MinHash + LSH mesh analysis detects trigger conflicts across 50+ skills in O(n). Doctor command shows health grades for your entire skill collection.

---

## What's New in v5.1

| Feature | Description |
|---------|-------------|
| Honest Scoring | "Structural Score" label everywhere — transparent about what's measured |
| Stemming Tokenizer | Suffix-stripping replaces fixed synonym tables |
| Beam Search | Top-3 exploration instead of greedy top-1 from iteration 4 |
| EMA Plateau Detection | Exponential Moving Average replaces fixed-window ROI |
| MinHash + LSH | O(n) mesh analysis instead of O(n^2) for 50+ skills |
| Context-aware Patches | Generates meaningful descriptions instead of TODOs |
| Doctor Command | `skillforge doctor` scans ALL installed skills |
| Dimension Guard | Prevents patches that tank a dimension by >15pt |
| Coherence Check | Instruction-assertion alignment as quality bonus |
| 40+ Pre-compiled Regex | Performance optimization across the scorer |
| Public Cache API | `invalidate_cache()` replaces direct `_file_cache.pop()` |

---

## Commands

### Core

| Command | What It Does |
|---------|--------------|
| `/skillforge` | Full autonomous loop with GOAL + METRIC |
| `/skillforge:doctor` | Scan ALL installed skills, show health summary |
| `/skillforge:auto` | Self-driving auto-improve (deterministic patches, no prompts) |
| `/skillforge:init` | Bootstrap eval suite + baseline from any SKILL.md |
| `/skillforge:report` | Generate shareable markdown report with badge |

### Analyze & Debug

| Command | What It Does |
|---------|--------------|
| `/skillforge:analyze` | One-shot gap analysis with ranked recommendations |
| `/skillforge:bench` | Establish quality baseline for a skill |
| `/skillforge:eval` | Run eval suite assertions |
| `/skillforge:mesh` | Detect trigger conflicts across all installed skills |
| `/skillforge:triage` | Cluster failures, auto-generate fixes |
| `/skillforge:log-failure` | Log a skill failure for later triage |
| `/skillforge:update` | Update SkillForge to latest version |

---

## How It Scores

Two modes, one decision:

**Structural Score** (default) — Instant, zero cost. Measures file organization, trigger keywords, eval coverage, edge cases, efficiency, composability. Catches 85% of issues. Use for fast iteration.

**Runtime Score** (`--runtime`) — Invokes Claude with test prompts, validates actual behavior against assertions. Use before shipping to production.

| Dimension | Weight | What It Measures |
|-----------|--------|-----------------|
| Structure | 15% | Frontmatter, headers, examples, progressive disclosure |
| Trigger Accuracy | 20% | TF-IDF keyword overlap against eval suite prompts |
| Eval Coverage | 20% | Assertion breadth and eval suite coverage |
| Edge Coverage | 15% | Edge case definitions in eval suite |
| Token Efficiency | 10% | Information density, signal-to-noise ratio |
| Composability | 5% | Scope boundaries, handoff declarations |
| Runtime *(opt-in)* | 15% | Actual Claude behavior against assertions |

Grades: **S** (>=95), **A** (>=85), **B** (>=75), **C** (>=65), **D** (>=50), **F** (<50).

Full scoring methodology: [docs/SCORING.md](docs/SCORING.md)

---

## Self-Score

SkillForge scores itself. Dogfooding, not marketing.

| Metric | Value |
|--------|-------|
| Structural Score | **99.9 / 100** [S] |
| Tests | **99/99 passing** (87 integration + 12 self) |
| Code review | **3 CRITICAL + 9 HIGH fixed** in v5.1.1 |
| Security | 27 + 12 fixes from multi-agent audits |
| Journey | v1.0 (62.5) → v5.1.1 (99.9) across 5 major versions |

---

## Ecosystem

`skill-creator` builds a v1 skill. SkillForge grinds it to production quality.

```
skill-creator → v1 SKILL.md → /skillforge:auto → autonomous grinding → ship
```

- **[skill-creator](https://github.com/anthropics/courses/tree/master/claude-code/09-skill-creator)** — generate the first draft
- **[autoresearch](https://github.com/uditgoenka/autoresearch)** — generalized autonomous research for Claude Code

---

## Badge

Score your skill and add this badge to your README:

```markdown
[![SkillForge: 99.9 [S]](https://img.shields.io/badge/SkillForge-99.9%2F100_%5BS%5D-brightgreen)](https://github.com/Zandereins/skillforge)
```

[![SkillForge: 99.9 [S]](https://img.shields.io/badge/SkillForge-99.9%2F100_%5BS%5D-brightgreen)](https://github.com/Zandereins/skillforge)

---

## Contributing

Found a bug in the scorer? Add a test case to `eval-suite.json` and open an issue.
Want to improve scoring logic? Edit `score-skill.py`, run `bash test-integration.sh`, and PR the diff.

---

## License

MIT — do whatever you want.

---

*Built by [Franz Paul](https://github.com/Zandereins) with Claude Code.*
