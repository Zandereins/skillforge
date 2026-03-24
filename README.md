# Schliff

The finishing cut for Claude Code skills.

<p align="center">
  <img src="demo/schliff-demo.gif?v=2" alt="Schliff improving a skill from 56.9 to 99.9" width="720">
</p>

```
Baseline:  █████░░░░░░░░░░░░░░░  54.0/100  [D]
After 18x: ████████████████████  98.3/100  [S]

What changed:
  Structure         70 → 100     Added description, examples, concrete commands
  Efficiency        35 → 93      Removed hedging language, improved density
  Composability     30 → 90      Added scope, error behavior, dependencies
  Clarity           90 → 100     Resolved vague references
```

> You wrote a skill. It worked. Three weeks later, triggers misfire, edge cases slip through, instructions contradict themselves. Schliff fixes all of it autonomously — deterministic patches, mechanical scoring, zero hallucinations.

[![GitHub stars](https://img.shields.io/github/stars/Zandereins/schliff?style=flat-square)](https://github.com/Zandereins/schliff)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/endpoint?url=https://gist.githubusercontent.com/Zandereins/130bb61237b5b9b1536718e6a2296d4a/raw/schliff-tests.json)](.github/workflows/test.yml)
[![Structural Score](https://img.shields.io/endpoint?url=https://gist.githubusercontent.com/Zandereins/130bb61237b5b9b1536718e6a2296d4a/raw/schliff-score.json)](skills/schliff/scripts/score-skill.py)
[![v6.0.0](https://img.shields.io/badge/Version-6.0.0-F59E0B)](CHANGELOG.md)
[![Claude Code Skill](https://img.shields.io/badge/Claude_Code-Skill-8A2BE2)](https://docs.anthropic.com/en/docs/claude-code/skills)

---

## Try It — 3 minutes, zero config

> **Note:** Schliff commands (`/schliff:*`) run inside [Claude Code](https://docs.anthropic.com/en/docs/claude-code), not in a regular terminal. The installer checks all prerequisites.

```bash
# 1. Install once (terminal, ~1 min)
git clone https://github.com/Zandereins/schliff.git && bash schliff/install.sh

# 2. Score the demo skill (Claude Code, ~10 sec)
/schliff:init demo/bad-skill/SKILL.md

# 3. Watch it grind to [S] (Claude Code, ~2 min)
/schliff:auto
```

**What you'll see:** 18 autonomous iterations. Each one: patch → measure → keep or revert. Score climbs from 56 [D] to 99.9 [S]. Stops when ROI plateaus. No prompts, no babysitting.

**Prerequisites:** Python 3.9+, Bash, Git, jq

Already have skills? Run `/schliff:doctor` to scan all installed skills and show health grades + token costs.

---

## What Schliff Fixes

Real improvements from the included demo skill:

| Problem | What Schliff does | Result |
|---------|-------------------|--------|
| Triggers misfire | Keyword matching + negative boundaries | **0% → 89%** accuracy |
| Missing structure | Added examples, edge cases, frontmatter | **75 → 100**/100 |
| Vague instructions | Replaced hedging with concrete commands | **35 → 93**/100 |
| No scope boundaries | Added handoff declarations + "do NOT use" | **40 → 100**/100 |

Automated. No human intervention. Stops when ROI plateaus.

---

## This Is For You If

- **Skill Creator** — Run `/schliff:init` on your v1 skill to get a baseline + eval suite
- **Skill Maintainer** — Run `/schliff:auto` to grind any skill from [C] to [S] overnight
- **Fleet Manager (10+ skills)** — Run `/schliff:doctor` to scan everything, detect conflicts + token costs
- **Quality Gate** — Run `/schliff:eval` before shipping, or use the [GitHub Action](#github-action) in CI

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

  Structural Score: ██████████████████░░  90.2/100  [A]
    [7/8 dimensions, 90% coverage]

  Dimensions:
    structure       ██████████  100/100
    triggers        █████████░   95/100
    quality         █████████░   91/100
    edges           ██████████  100/100
    efficiency      ████████░░   84/100
    composability   █████░░░░░   50/100
    clarity         ██████████  100/100
======================================================================
```
</details>

<details>
<summary><b>Auto-Improve</b> — Autonomous grinding with EMA-based stopping</summary>

```
Scoring baseline...
Baseline: 90.2/100 (7 dims)

--- Iteration 1 ---
  [composability] +5.0  Added error behavior description
  Score: 90.2 → 92.1  ██████████████████░░  [A]  KEEP

--- Iteration 3 ---
  [composability] +3.0  Added dependency declarations
  Score: 92.1 → 94.8  ███████████████████░  [A]  KEEP

  Schliff Auto-Improve Complete
  ──────────────────────────────────────────────────
  Score:  90 → 94.8/100  ███████████████████░  (+4.6)  [A]
  Iters:  3  |  Kept: 2  |  Time: 12s
  Stop:   EMA plateau (ROI < 0.5)
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
  schliff                   90    [A]    7/8       0  Healthy

  Mesh Health: 68/100 (4 cross-skill issues)
  Run /schliff:mesh for details.

  NOTE: Scores are STRUCTURAL — they measure file organization,
  not runtime effectiveness. Use --runtime for validated scoring.
======================================================================
```
</details>

<details>
<summary><b>What's New in v6.0</b></summary>

| Feature | Description |
|---------|-------------|
| Rebrand to Schliff | "The finishing cut" — German for polish/grind |
| Clarity as Default | 7th dimension always active (contradictions, vague refs, ambiguity) |
| Token Cost Estimation | Doctor shows per-skill token cost + fleet total |
| GitHub Action | `Zandereins/schliff@v6` — CI quality gate with PR comments |
| pip CLI | `schliff score SKILL.md` — works without Claude Code |
| Actionable Doctor | Copy-paste commands with full skill paths |
| Trigger Confidence | Small eval suites (<8 triggers) capped at score 60 |
| Context-aware Contradictions | "run tests" vs "run tests in production" distinguished |
| Anti-gaming | Empty headers, repetitive markers, binary composability fixed |
| 340+ Tests (unit + integration + proof) | +3 for token estimation, context contradictions |
| 40 Security Fixes | Shell injection, prompt injection, ReDoS, supply chain |

</details>

---

## Quality & Security

Schliff scores itself — 7 dimensions, same engine, no exceptions.

| Metric | Value | What This Means |
|--------|-------|-----------------|
| Structural Score | **95.4 / 100** [S] | Production-ready. 10 composability sub-checks, all passing. |
| Tests | **340+ passing** | 219 unit + 101 integration + 14 self + 6 proof. Every scorer rule tested. |
| Security | **40 fixes** | Shell injection, prompt injection, ReDoS, supply chain. |
| Dimensions | **7 + runtime** | Transparent, rule-based, explainable scoring. |
| Journey | v1.0 (62.5) → v6.0 (95.4) | 7 major versions. Continuous improvement, no regressions. |

[Scoring methodology](docs/SCORING.md) | [Security details](CHANGELOG.md)

---

## GitHub Action

Score skills in CI. Block PRs that regress. The Codecov for SKILL.md files.

```yaml
- uses: Zandereins/schliff@v6
  with:
    skill-path: '.claude/skills/my-skill/SKILL.md'
    minimum-score: '75'      # blocks PR if below
    comment-on-pr: 'true'    # posts score table on PR
```

---

## CLI

Score any skill without Claude Code:

```bash
pip install schliff

schliff score path/to/SKILL.md          # score a skill
schliff score path/to/SKILL.md --json   # JSON output
schliff doctor                           # scan all installed skills
```

---

## Ecosystem

`skill-creator` builds a v1 skill. Schliff grinds it to production quality.

```
skill-creator → v1 SKILL.md → /schliff:auto → autonomous grinding → ship
```

- **[skill-creator](https://github.com/anthropics/courses/tree/master/claude-code/09-skill-creator)** — generate the first draft
- **[autoresearch](https://github.com/uditgoenka/autoresearch)** — generalized autonomous research for Claude Code

---

## Badge

Score your skill and add this to your README:

```markdown
[![Schliff: 90 [A]](https://img.shields.io/badge/Schliff-90%2F100_%5BA%5D-green)](https://github.com/Zandereins/schliff)
```

[![Schliff: 90 [A]](https://img.shields.io/badge/Schliff-90%2F100_%5BA%5D-green)](https://github.com/Zandereins/schliff)

---

## Contributing

Found a bug in the scorer? Add a test case to `eval-suite.json` and open an issue.
Want to improve scoring logic? Edit `score-skill.py`, run `bash test-integration.sh`, and PR the diff.

---

## Next Steps

1. [Try the 3-minute demo](#try-it--3-minutes-zero-config) — see a skill go from [D] to [S]
2. Run `/schliff:doctor` on your own skills — instant health check
3. Add the [GitHub Action](#github-action) to your CI — quality gate for every PR
4. [Read the scoring methodology](docs/SCORING.md) — understand what each dimension measures

Questions? [Open an issue](https://github.com/Zandereins/schliff/issues) — we respond fast.

---

## License

MIT — do whatever you want.

---

*Built by [Franz Paul](https://github.com/Zandereins) with Claude Code.*
