# Schliff Architecture

System design, file tree, data flow, and implementation details.

---

## File Tree

```
skills/schliff/
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
│   ├── verify.py               # CI gate — exit 0/1/2, --min-score, --regression
│   ├── cli.py                  # pip CLI router (score, verify, doctor, badge, demo, version)
│   ├── shared.py               # Shared utilities (read, extract, validate)
│   ├── nlp.py                  # Tokenization, stemming, synonyms
│   ├── run-eval.sh             # Binary assertion engine
│   ├── progress.py             # Convergence analysis
│   ├── runtime-evaluator.py    # Live Claude invocation testing
│   ├── test-integration.sh     # 99 integration tests
│   └── test-self.sh            # 20 self-tests (dogfooding)
├── tests/
│   ├── unit/                   # 427 unit tests (pytest)
│   └── proof/                  # 6 proof-of-work tests
├── hooks/
│   └── session-injector.js     # Surfaces failures at session start
└── templates/
    └── eval-suite-template.json
```

---

## Key Modules and Responsibilities

### score-skill.py — The Scorer

Central scoring engine. Computes a composite structural score across 7 dimensions (structure, triggers, quality, edges, efficiency, composability, clarity) plus an optional runtime dimension. All dimension functions return `{"score": int, "issues": list, "details": dict}`. A score of `-1` means "not applicable / skipped" — the dimension is excluded from the composite.

Features:
- 40+ pre-compiled regex patterns for performance
- Suffix-stripping stemmer for morphological matching
- Synonym expansion table for non-morphological matches
- TF-IDF-inspired trigger scoring with domain signal detection
- File cache with size limits (`MAX_CACHE_ENTRIES = 500`, `MAX_SKILL_SIZE = 1 MB`)
- Public cache API (`invalidate_cache()`) for external callers
- Auto-calibrated weights from `~/.schliff/meta/calibrated-weights.json`
- Custom weight override via `--weights`

### auto-improve.py — The Loop

Autonomous improvement engine. Scores a baseline, identifies the highest-impact fixes via `text-gradient.py`, applies patches, re-scores, and keeps or reverts each change. Stops when the EMA plateau detector fires (diminishing returns over consecutive windows).

Key behaviors:
- Deterministic patches first (frontmatter, noise removal, TODO cleanup) — no LLM needed
- Beam search (top-3 exploration) from iteration 4 onward
- Dimension guard: rejects patches that tank a single dimension by >15 points
- Parallel branching via git worktrees when stuck (5+ consecutive discards)

### text-gradient.py — The Fixer

Identifies specific improvements with predicted score deltas. Generates deterministic patches (frontmatter insertions, noise removal, scope boundary additions) and context-aware patches (meaningful descriptions instead of TODOs). ~60-70% of all fixes are fully deterministic.

### dashboard.py — Health Dashboard

Renders colored gauges, grade badges, dimension bars, top-N improvement recommendations with predicted deltas, and achievement progress. Single-skill view with full breakdown.

### doctor.py — Multi-Skill Scanner

Scans ALL installed skills in one pass. Finds every `SKILL.md` under `~/.claude/skills/`, scores each one, shows a summary table with grades and issue counts. Delegates to `skill-mesh.py` for cross-skill conflict detection.

### skill-mesh.py — Conflict Detection

Analyzes trigger overlaps and scope collisions across all installed skills. Uses MinHash + LSH for O(n) analysis (instead of O(n^2)) when dealing with 50+ skills. Generates actionable fix recommendations, not just a report. Deterministic results via `hashlib.sha256` instead of `hash()`.

### episodic-store.py — Cross-Session Memory

TF-IDF semantic search across all past improvement sessions. Stores what strategies worked, for which skill domains, and under what conditions. Size-capped with automatic consolidation. Used by the strategy predictor to recommend approaches before trying them.

### meta-report.py — Strategy Predictor

Groups improvement history by `(domain, strategy_type, gap_bucket)` and computes success probability. Recommends strategies based on past performance data. Also handles weight calibration from runtime data.

### parallel-runner.py — Worktree Experiments

When the improvement loop gets stuck (5+ consecutive discards), spins up 3 parallel strategies via git worktrees and keeps the best result. Each worktree runs an independent improvement path.

### init-skill.py — Bootstrapper

Auto-discovers `SKILL.md` from the current directory or a provided path. Generates an eval suite from the skill content (triggers, test cases, edge cases). Shows colored dimension bars and contextual next steps.

### generate-report.py — Report Generator

Creates shareable markdown reports with before/after tables, ASCII dimension heatmaps across iterations, achievement badges, and improvement recommendations.

### terminal_art.py — Render Library

Shared library for terminal output: grade badges, dimension heatmaps, progress bars, colored gauges. Used by dashboard, reports, and init.

### achievements.py — Badge Tracker

10 unlockable achievement badges tracked per-skill. Milestones like first improvement, reaching specific grades, full dimension coverage. Shown in dashboard and reports.

### run-eval.sh — Assertion Engine

Binary assertion runner. Executes eval suite test cases and edge cases, checking assertions against expected values. Returns pass/fail counts.

### runtime-evaluator.py — Live Testing

Invokes Claude CLI with test prompts and checks responses against `response_*` assertions. Used by the `--runtime` flag and `/schliff:eval`.

---

## Underscore Aliases

Python module names cannot contain hyphens. Scripts with hyphens in their names (e.g., `score-skill.py`) cannot be imported directly by other Python files. Underscore aliases (e.g., `score_skill.py`) exist as thin wrappers that re-export the hyphenated module's contents, enabling standard Python imports:

```python
# This works because score_skill.py exists as an alias
from score_skill import compute_composite
```

Aliases exist for: `score_skill`, `text_gradient`, `skill_mesh`, `parallel_runner`.

---

## Data Flow: The Improvement Loop

```
SKILL.md
   │
   ▼
┌─────────────┐
│  score-skill │ ── Computes 7-dimension baseline
└──────┬──────┘
       │
       ▼
┌──────────────┐
│ text-gradient │ ── Identifies highest-impact fix with predicted delta
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  auto-improve │ ── Applies patch to SKILL.md
└──────┬───────┘
       │
       ▼
┌─────────────┐
│  score-skill │ ── Re-scores after patch
└──────┬──────┘
       │
       ▼
  ┌─────────┐
  │ Keep or  │ ── Score improved? Keep. Regressed? Revert.
  │ Revert?  │    Dimension tanked >15 pts? Revert (dimension guard).
  └────┬────┘
       │
       ▼
  ┌──────────┐
  │ Continue  │ ── EMA plateau? Stop. Otherwise next iteration.
  │ or Stop?  │    Stuck 5+ discards? Try parallel branching.
  └──────────┘
```

Cross-session learning:
- `episodic-store.py` records what worked after each session
- `meta-report.py` predicts best strategies for next session
- Calibrated weights feed back into `score-skill.py`

---

## Hook System: session-injector.js

The session injector is a Claude Code hook that runs at session start (`type: "init"`). It reads from `<cwd>/.schliff/failures.jsonl` and injects a failure summary as `additionalContext` when 3 or more untriaged failures exist.

Behavior:
1. Reads stdin JSON: `{"session_id": "...", "cwd": "...", "type": "init"}`
2. Resolves `cwd` to an absolute path, validates it is an existing directory
3. Reads `<cwd>/.schliff/failures.jsonl` (JSONL format, max 1 MB)
4. Filters for untriaged entries (entries without `injected: true`)
5. If >= 3 untriaged failures: clusters by `skill:failure_type`, builds summary, outputs `{"additionalContext": "..."}`
6. Marks processed entries as `injected: true` using atomic write (tmp + rename)
7. If < 3 untriaged failures: outputs `{}`

Security measures:
- Field sanitization: strips ASCII control chars, Unicode bidi/zero-width chars, truncates to 120 chars
- Prototype stripping: removes `__proto__`, `constructor`, `prototype` from parsed JSON
- Size limit: skips files > 1 MB
- Malformed JSONL lines are skipped with a stderr warning

---

## Implementation Notes

### Atomic Writes

All file writes across Schliff use the `.tmp` + `rename()` pattern. Content is written to a temporary file first, then atomically renamed to the target path. This prevents skill file corruption if the process crashes mid-write.

This applies to:
- SKILL.md patches during auto-improve
- failures.jsonl updates in the session injector
- Any JSON/JSONL output files

### Regex Guards

All regex operations on user-provided data are guarded against `re.error`. If a user's skill file contains content that would cause a regex to fail, the scorer catches the exception and returns a safe default rather than crashing.

### Encoding

All JSON reads specify `encoding="utf-8"` explicitly. File reads use `errors="replace"` to handle non-UTF-8 content gracefully instead of crashing.

### File Cache

`score-skill.py` maintains a module-level file cache to avoid redundant reads within a single invocation. The cache is bounded at 500 entries (`MAX_CACHE_ENTRIES`) with FIFO eviction. External callers should use `invalidate_cache(skill_path)` instead of accessing `_file_cache` directly.

### Skill File Size Limit

Skill files larger than 1 MB (`MAX_SKILL_SIZE`) are rejected to prevent DoS via large inputs. The session injector enforces the same limit on `failures.jsonl`.
