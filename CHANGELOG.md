# Changelog

All notable changes to Schliff are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/).

## [6.3.0] - 2026-03-26

### Added
- `schliff diff <path>` command — show score delta vs. previous commit (or any `--ref`)
  - Ref validation (prevents git flag injection), path containment check, size limit guard
  - Human-readable and `--json` output formats
- CLI quick-start epilog — `schliff` without args now shows demo/score/doctor hints
- Case study: ShieldClaw (OpenClaw plugin) — 68.3 [C] → 94.6 [A] in 1 round, cross-ecosystem proof
- 85 new tests: cmd_diff (18), composite weights (33), diff scoring (34)
- README: context bridge explaining Claude Code for non-users
- README: commands table split into CLI (standalone) vs Claude Code (require integration)
- README: "Where Schliff fits" ecosystem diagram moved to Quick Start section

### Fixed
- Scoring: trigger precision/recall reported 100.0 when no predictions existed (now 0.0)
- Scoring: clarity scorer skipped ambiguous pronoun detection on first line (i==0 case)
- Scoring: efficiency scorer returned float instead of int (inconsistent with other dimensions)
- README: self-score rewording removes circular "99.0/100" claim
- README: anti-gaming section honestly frames benchmark as self-designed suite
- README: triggers description corrected from "conflicts between skills" to "eval-suite trigger accuracy"
- README: test count updated to actual 540 unit + 99 integration with links
- Security: `score_diff()` now receives resolved absolute path instead of raw user input
- Docs: stale test counts in ARCHITECTURE.md and CONTRIBUTING.md updated

## [6.2.0] - 2026-03-25

### Added
- `schliff demo` command — score a built-in bad skill to see schliff in action instantly
- `schliff badge <path>` command — generate copy-paste markdown badge for READMEs
- Pre-commit hook support (`.pre-commit-hooks.yaml`) for automatic skill quality gates
- Doctor: `--verbose` flag shows per-skill issues, `references/` extraction recommendation for large skills
- Community case study: @wan-huiyan agent-review-panel (64→85.6, 75% token reduction, A/B validated)
- 24 new tests for demo, badge, ReDoS fix, clarity injection, JSON rounding (455 total)
- Show HN launch draft (`docs/specs/show-hn-draft.md`)

### Fixed
- Security: ReDoS in `_RE_ERROR_BEHAVIOR` — bounded `[\w\s]+` to `\w[\w ]{0,80}`
- Security: OOM-safe eval-suite loading — `stat().st_size` check before `read_text()`
- Security: symlink rejection on `references/` directory and files in `estimate_token_cost`
- Scoring: `no_real_examples` silently suppressed when `code_block_pairs >= 6`
- Scoring: clarity auto-injection with custom weights — custom weights now take full precedence
- CLI: `schliff auto` reference corrected to `/schliff:auto` (Claude Code slash command)
- CLI: JSON dimension scores rounded to 1 decimal (was outputting raw floats like 92.0501...)
- CLI: badge URL encoding with `safe=""` (forward slash was not percent-encoded)
- Pre-commit: `pass_filenames: true` with file filter (was `false`, causing argparse crash)
- Removed unused `score_coherence` from public API exports
- Removed dead `SCRIPT_DIR` assignments in doctor.py and skill_mesh.py
- Fixed stale BUG DOCUMENTED comments in test_edge_cases.py

### Changed
- Quick Start: reordered to demo → doctor → score for better onboarding
- README: GIF uses absolute GitHub raw URL (fixes broken image on PyPI)
- README: Mermaid diagram section includes "view on GitHub" hint for PyPI
- PyPI metadata: added Homepage, Documentation URLs, Environment::Console classifier
- GitHub: topics reduced from 20 to 10, homepage URL set to PyPI

## [6.1.0] - 2026-03-24

### Added
- Description-aware trigger generation in init-skill (Issue #13)
- Precision/recall reporting in trigger scorer
- `schliff verify` command for CI integration (exit 0/1/2, --min-score, --regression)
- Anti-gaming benchmark with 6 synthetic skills (6/6 detected)
- Repetition detection in efficiency scorer (repeated identical lines count as noise)
- Screenshot-ready `schliff score` output with per-dimension bars and status words
- 100+ new tests (init-skill, precision/recall, verify, terminal_art, anti-gaming)
- 10 new eval-suite test cases (tc-8..tc-17) with 66 coherence-covering assertions

### Changed
- SKILL.md compressed by 13% (1676→1455 words) without information loss
- Self-score: 95.7 → 99.0/100 [S] (quality 91→99 via coherence, efficiency 88→92 via compression)

### Fixed
- Init script no longer generates Schliff-specific triggers for non-Schliff skills
- Structural markers (code fences, headers, horizontal rules) excluded from repetition count
- Code block content excluded from repetition counting (prevents false positives on examples)
- `load_last_score` handles corrupted history entries without crashing
- `run_verify` returns exit code 2 on file-not-found and scorer errors
- ANSI reset constant used consistently in terminal_art output
- 10 bugs from 5-agent security audit (shell injection, prompt injection, ReDoS guards)
- Composability handoff pattern restored (was dropped during SKILL.md compression)

## [6.0.0] - 2026-03-24

### Changed
- **Rebrand: SkillForge → Schliff** — "the finishing cut" (German: den letzten Schliff geben)
- All `/skillforge:*` commands renamed to `/schliff:*`
- All internal references, paths, demo files updated

### Added
- **Clarity as default dimension** — 7th dimension always active (5% weight, opt-out via `--no-clarity`)
- **Token cost estimation** — Doctor shows per-skill token cost + fleet total
- **GitHub Action** — `Zandereins/schliff@v6` scores skills in CI, comments on PRs
- **pip CLI** — `schliff score SKILL.md` works without Claude Code
- **Actionable Doctor** — copy-paste commands with full skill paths
- **Trigger confidence cap** — eval suites with <8 triggers capped at score 60
- **Context-aware contradictions** — "run tests" vs "run tests in production" distinguished
- **Anti-gaming headers** — empty sections don't count toward structure score
- **Signal caps** — efficiency can't be gamed with repetitive markers
- **Star badge** — GitHub stars visible in README
- **"What Schliff Fixes" table** — concrete before/after improvements
- **"Quality & Security" section** — trust signals front-loaded with "What This Means"
- **"Next Steps" CTAs** — clear paths forward for visitors
- 3 new unit tests (token estimation, context contradictions)

### Fixed
- Trigger threshold floor prevents false positives on small eval suites
- Missing dimension warnings always shown (except opt-in runtime)
- Clarity false positives on same verb with different context

### Breaking
- `--clarity` flag removed (clarity is now default; use `--no-clarity` to opt out)

## [5.1.1] - 2026-03-22

### Fixed
- Atomic file writes in text-gradient.py (prevents skill corruption on crash)
- `re.error` guard on all user-controlled regex patterns
- Path traversal validation before skill file writes
- `from __future__` placement after docstrings in 3 files
- Unguarded `terminal_art.progress_bar` import with fallback stub
- Broken all-errors guard using zip identity check
- Missing `encoding="utf-8"` on eval-suite JSON reads (4 call sites)
- Unvalidated `diff_ref` parameter in git subprocess calls
- Severity filter bypass on mesh cache hit
- `terminal_art` import before `sys.path` setup in dashboard
- Non-deterministic `hash()` replaced with `hashlib.sha256` in LSH banding
- `progress.py` loaded once instead of 3 times in report generator

## [5.1.0] - 2026-03-22

### Added
- **Honest Scoring** — "Structural Score" label everywhere, replacing misleading "Quality Score"
- **Stemming Tokenizer** — suffix-stripping replaces fixed synonym tables for better keyword matching
- **Beam Search** — top-3 exploration instead of greedy top-1 from iteration 4 onward
- **EMA Plateau Detection** — Exponential Moving Average replaces fixed-window ROI stopping
- **MinHash + LSH** — O(n) mesh analysis instead of O(n^2) for 50+ skills
- **Context-aware Patches** — generates meaningful descriptions instead of TODOs
- **Doctor Command** (`doctor.py`) — scans all installed skills, shows health summary with grades
- **Dimension Guard** — prevents patches that tank a single dimension by >15 points
- **Coherence Check** — instruction-assertion alignment as quality bonus
- **40+ Pre-compiled Regex** — performance optimization across the scorer
- **Public Cache API** — `invalidate_cache()` replaces direct `_file_cache.pop()`
- **Underscore Alias Modules** — `score_skill.py`, `text_gradient.py`, `skill_mesh.py`, `parallel_runner.py` for Python import compatibility

### Fixed
- State truncation bug in auto-improve loop
- EMA indexing off-by-one in plateau detection
- Deterministic hash for MinHash reproducibility

## [5.0.0] - 2026-03-21

### Added — The Self-Driving Engine
- **Auto-Apply** (`text-gradient.py --apply`) — deterministic patches apply themselves without LLM
- **Auto-Improve** (`auto-improve.py`) — autonomous loop driver: score → gradient → apply → keep/revert → repeat
- **Strategy Predictor** (`meta-report.py predict_best_strategy()`) — predicts P(keep) before trying
- **Runtime Scoring** (`score-skill.py --runtime`) — 7th dimension invokes Claude for behavioral validation
- **Auto-Calibration** (`meta-report.py compute_optimal_weights()`) — dimension weights from data
- **Mesh Evolution** (`skill-mesh.py generate_mesh_actions()`) — generates negative boundaries, stubs, scope fixes
- **Incremental Mesh** (`skill-mesh.py --incremental`) — content-hash caching, O(n×changed) not O(n²)
- **Episodic Memory** (`episodic-store.py`) — cross-session TF-IDF recall with auto-consolidation
- **Parallel Branching** (`parallel-runner.py`) — git worktree experiments, 3 strategies at once
- **ROI Stopping** — marginal ROI < 0.2 for 3 windows → auto-stop
- **Gap Buckets** (`progress.py`) — dimension gaps discretized for predictor input
- **Episode Emit** (`progress.py`) — auto-emit learnings to episodic store after decisions
- New subcommands: `/schliff:auto`, `/schliff:mesh-evolve`, `/schliff:predict`, `/schliff:recall`

### Changed
- Dimension weights redistributed: triggers 25%→20%, quality 25%→20%, composability 10%→5%, new runtime 15%
- `compute_composite()` auto-loads `calibrated-weights.json` when available
- Scorer test updated: 7 dimensions (6 core + runtime opt-in)

## [4.1.0] - 2026-03-21

### Fixed
- 3 critical + 4 high security issues from 4-agent code review
- CI stability with `--no-runtime-auto` in self-tests

## [3.1.0] - 2026-03-20

### Fixed
- `--since` flag now correctly scopes all 11 methods in `progress.py`
- Consistent score capping across all scoring functions

### Added
- Cost tracking: real `duration_ms`, `tokens_estimated`, `delta`, computed `status`
- 25 new integration tests (51 total)
- `explain_score_change()` wired into `--diff` output
- Security: path traversal guard, file size limit (1MB), ReDoS protection
- CHANGELOG.md, SECURITY.md, GitHub CI workflow

### Removed
- Dead code: `history/results.tsv`
- Shell expansion risk: replaced `xargs` with `sed` in `run-eval.sh`

## [3.0.0] - 2026-03-20

### Added
- Runtime evaluator — invoke Claude with test prompts
- Diff-aware scoring (`--diff` flag)
- Strategy meta-learning in `progress.py`
- Instruction clarity scorer (`--clarity` flag)
- Eval health classification
- 26-test integration suite + 12-test self-test suite

### Fixed
- 7 critical bugs found by sparring agents
- 3 assertion type mismatches
- 2 crash bugs, clarity false positives

## [2.3.0] - 2026-03-19

### Added
- Bidirectional synonym expansion, plateau guard, interaction effect detection

## [2.0.0] - 2026-03-18

### Added
- TF-IDF trigger scoring, composability analysis, 9-phase protocol
- Discovery mode, parallel experimentation, noisy metric handling

## [1.0.0] - 2026-03-17

### Added
- Initial release — 6-dimension scoring, eval runner, progress tracking
