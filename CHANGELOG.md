# Changelog

All notable changes to SkillForge are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/).

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
