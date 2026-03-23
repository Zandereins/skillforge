# Schliff

The finishing cut for Claude Code skills.

<p align="center">
  <img src="demo/schliff-demo.gif?v=2" alt="Schliff improving a skill from 56.9 to 99.9" width="720">
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

> You wrote a skill. It worked. Three weeks later, triggers misfire, edge cases slip through, instructions contradict themselves. Schliff fixes all of it autonomously — deterministic patches, mechanical scoring, zero hallucinations.

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/endpoint?url=https://gist.githubusercontent.com/Zandereins/130bb61237b5b9b1536718e6a2296d4a/raw/schliff-tests.json)](skills/schliff/scripts/test-integration.sh)
[![Structural Score](https://img.shields.io/endpoint?url=https://gist.githubusercontent.com/Zandereins/130bb61237b5b9b1536718e6a2296d4a/raw/schliff-score.json)](skills/schliff/scripts/score-skill.py)
[![v6.0.0](https://img.shields.io/badge/Version-6.0.0-F59E0B)](CHANGELOG.md)
[![Claude Code Skill](https://img.shields.io/badge/Claude_Code-Skill-8A2BE2)](https://docs.anthropic.com/en/docs/claude-code/skills)

---

## Try It

> **Note:** Schliff commands (`/schliff:*`) run inside [Claude Code](https://docs.anthropic.com/en/docs/claude-code), not in a regular terminal.

```bash
# 1. Install (in your regular terminal)
git clone https://github.com/Zandereins/schliff.git && bash schliff/install.sh

# 2. Score the included demo skill (in Claude Code)
/schliff:init demo/bad-skill/SKILL.md

# 3. Watch it improve autonomously (in Claude Code)
/schliff:auto
```

**What you'll see:** The score climbs from 56 [D] through [C], [B], [A] to [S] as Schliff applies patches, checks each delta, and reverts anything that regresses. When ROI drops below threshold, it stops.

**Prerequisites:** Python 3.9+, Bash, Git, jq — the installer checks all of these.

Already have skills? Run `/schliff:doctor` to see health grades for all your installed skills at once.

**Add this badge to your README after scoring:**

```markdown
[![Schliff: 97 [S]](https://img.shields.io/badge/Schliff-97%2F100_%5BS%5D-brightgreen)](https://github.com/Zandereins/schliff)
```

---

## This Is For You If

- **Skill Creator** — Run `/schliff:init` on your v1 skill to get a baseline + eval suite
- **Skill Maintainer** — Run `/schliff:auto` to grind any skill from [C] to [S] overnight
- **Fleet Manager (10+ skills)** — Run `/schliff:doctor` to scan everything, detect conflicts
- **Quality Gate** — Run `/schliff:eval` before shipping to validate assertions pass

---

## Why It Works

**Autonomous** — Runs unattended. Applies patches, measures delta, reverts regressions, stops when ROI drops. No prompts, no babysitting.

**Deterministic** — 60-70% of fixes are rule-based: frontmatter insertion, noise removal, TODO cleanup. No LLM needed. Same input, same output.

**Empirical** — 7 scoring dimensions (structure, triggers, quality, edges, efficiency, composability, clarity) + optional runtime validation against actual Claude behavior.

**Learns** — Episodic memory remembers which strategies worked across sessions. Predicts success before trying. Your 50th skill improves faster than your 1st.

**Scales** — MinHash + LSH mesh analysis detects trigger conflicts across 50+ skills in O(n). Doctor command shows health grades for your entire skill collection.

---

## Autoresearch for Claude Code

Inspired by [Karpathy's autoresearch](https://github.com/karpathy/autoresearch) (50K+ stars) — Schliff applies the same autonomous improvement loop to Claude Code skills:

| | Karpathy's autoresearch | Schliff |
|---|---|---|
| **Target** | ML training scripts | Claude Code SKILL.md files |
| **Metric** | 1 (val_bpb) | 7 dimensions |
| **Patches** | 100% LLM | 60-70% deterministic |
| **Memory** | None | Cross-session episodic store |
| **Fleet** | 1 file | 50+ skills (Doctor + Mesh) |

Both run overnight. Both stop when ROI plateaus. Both improve unattended.

---

## Commands

### Core

| Command | What It Does |
|---------|--------------|
| `/schliff` | Full autonomous loop with GOAL + METRIC |
| `/schliff:doctor` | Scan ALL installed skills, show health summary |
| `/schliff:auto` | Self-driving auto-improve (deterministic patches, no prompts) |
| `/schliff:init` | Bootstrap eval suite + baseline from any SKILL.md |
| `/schliff:report` | Generate shareable markdown report with badge |

### Analyze & Debug

| Command | What It Does |
|---------|--------------|
| `/schliff:analyze` | One-shot gap analysis with ranked recommendations |
| `/schliff:bench` | Establish quality baseline for a skill |
| `/schliff:eval` | Run eval suite assertions |
| `/schliff:mesh` | Detect trigger conflicts across all installed skills |
| `/schliff:triage` | Cluster failures, auto-generate fixes |
| `/schliff:log-failure` | Log a skill failure for later triage |
| `/schliff:update` | Update Schliff to latest version |

---

<details>
<summary><b>How It Scores</b> — 7 dimensions + optional runtime</summary>

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
| Composability | 10% | Scope boundaries, handoff declarations |
| Clarity | 5% | Contradiction detection, vague references, ambiguity |
| Runtime *(opt-in)* | 10% | Actual Claude behavior against assertions |

Grades: **S** (>=95), **A** (>=85), **B** (>=75), **C** (>=65), **D** (>=50), **E** (>=35), **F** (<35).

Full scoring methodology: [docs/SCORING.md](docs/SCORING.md)

</details>

<details>
<summary><b>Dashboard</b> — Health overview for any skill</summary>

```
======================================================================
  Schliff Health Dashboard: schliff
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

  Schliff Auto-Improve Complete
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
  Schliff Doctor — Skill Health Check
======================================================================

  1 skills scanned | 1 healthy | 4 mesh issues

  Skill                      Score  Grade   Dims  Issues  Action
  --------------------------------------------------------------------
  schliff                  100    [S]    6/7       0  Healthy

  Mesh Health: 68/100 (4 cross-skill issues)
  Run /schliff:mesh for details.

  NOTE: Scores are STRUCTURAL — they measure file organization,
  not runtime effectiveness. Use --runtime for validated scoring.
======================================================================
```
</details>

<details>
<summary><b>What's New in v5.3</b></summary>

| Feature | Description |
|---------|-------------|
| Context-aware Contradictions | Clarity distinguishes "run tests" vs "run tests in production" |
| Missing Dimension Warnings | Composite warns when eval-dependent dimensions are unmeasured |
| Trigger Threshold Floor | Small eval suites (1-4 triggers) can't produce false positives |
| Anti-gaming Headers | Empty sections don't count toward structure score |
| Signal Caps | Efficiency can't be gamed with repetitive "example" markers |
| 120 Unit Tests | +1 context-aware contradiction test |
| Honest Scoring | "Structural Score" label everywhere — transparent about what's measured |
| Stemming Tokenizer | Suffix-stripping replaces fixed synonym tables |
| Beam Search | Top-3 exploration instead of greedy top-1 from iteration 4 |
| EMA Plateau Detection | Exponential Moving Average replaces fixed-window ROI |
| MinHash + LSH | O(n) mesh analysis instead of O(n^2) for 50+ skills |
| 40 Security Fixes | Shell injection, prompt injection, ReDoS, supply chain |

</details>

---

## Self-Score

Schliff scores itself. Dogfooding, not marketing.

| Metric | Value |
|--------|-------|
| Structural Score | **97.1 / 100** [S] |
| Tests | **120 passing** (unit + integration + proof) |
| Security audit | **40 fixes** across 6 review rounds |
| Scoring engine | **7 dimensions**, continuous density, context-aware contradiction detection |
| Journey | v1.0 (62.5) → v6.0.0 (97.1) across 7 major versions |

---

## Ecosystem

`skill-creator` builds a v1 skill. Schliff grinds it to production quality.

```
skill-creator → v1 SKILL.md → /schliff:auto → autonomous grinding → ship
```

- **[skill-creator](https://github.com/anthropics/courses/tree/master/claude-code/09-skill-creator)** — generate the first draft
- **[autoresearch](https://github.com/uditgoenka/autoresearch)** — generalized autonomous research for Claude Code

---

## Contributing

Found a bug in the scorer? Add a test case to `eval-suite.json` and open an issue.
Want to improve scoring logic? Edit `score-skill.py`, run `bash test-integration.sh`, and PR the diff.

---

## License

MIT — do whatever you want.

---

*Built by [Franz Paul](https://github.com/Zandereins) with Claude Code.*
