# Contributing to Schliff

Thanks for your interest in improving Schliff! This guide covers everything you need to get started.

## Quick Setup

```bash
# Clone and install in dev mode (symlink)
git clone https://github.com/Zandereins/schliff.git
cd schliff
bash install.sh --link

# Run the test suite
make test-all
```

## Prerequisites

- Python 3.9+
- Bash 4.0+
- Git 2.0+
- jq 1.6+

## Project Structure

```
skills/schliff/
├── scripts/
│   ├── scoring/          # Scoring package (1 module per dimension)
│   │   ├── __init__.py   # Public API — import from here
│   │   ├── patterns.py   # Shared regex patterns
│   │   ├── structure.py  # Structure scoring
│   │   ├── triggers.py   # Trigger accuracy scoring
│   │   └── ...           # One file per dimension
│   ├── shared.py         # Core utilities (caching, file I/O, security)
│   ├── nlp.py            # NLP utilities (tokenization, stemming)
│   ├── terminal_art.py   # Terminal rendering (grades, bars, heatmaps)
│   └── ...               # Application scripts
├── commands/schliff/  # Claude Code command definitions
├── references/           # Deep documentation
├── templates/            # Eval suite templates
└── tests/proof/          # Proof tests
```

## Running Tests

```bash
make test          # 99 integration tests
make test-self     # 20 self-tests (Schliff scores itself)
make test-proof    # 6 proof tests (demonstrates real improvement)
make test-all      # All of the above + 540 unit tests (pytest)
make score         # Score Schliff's own SKILL.md (expect >= 90)
```

All tests must pass before submitting a PR.

## Adding a New Scoring Dimension

1. Create `scripts/scoring/your_dimension.py`:
   ```python
   """scoring/your_dimension.py — Your Dimension scoring."""
   from shared import read_skill_safe
   from scoring.patterns import _RE_YOUR_PATTERNS  # if needed

   def score_your_dimension(skill_path: str, eval_suite=None) -> dict:
       """Score your dimension.

       Returns dict with 'score' (0-100), 'issues' (list), 'details' (dict).
       """
       content = read_skill_safe(skill_path)
       # ... scoring logic ...
       return {"score": score, "issues": issues, "details": details}
   ```

2. Register in `scripts/scoring/__init__.py`:
   ```python
   from scoring.your_dimension import score_your_dimension
   ```

3. Add weight in `scripts/scoring/composite.py` (DEFAULT_WEIGHTS dict)

4. Add tests in `scripts/test-integration.sh`

5. Run `make test-all` to verify

## Code Style

- **Python 3.9+** — Use type hints, f-strings, pathlib
- **Line length:** 120 chars (configured in pyproject.toml)
- **Linter:** `make lint` (uses ruff)
- **Docstrings:** Required for all public functions
- **Error handling:** Always explicit — no silent failures
- **File I/O:** Use `shared.read_skill_safe()` for skill files (enforces size limits)
- **Regex:** Use `shared.validate_regex_complexity()` before executing user-supplied patterns

## Naming Conventions

- **Underscore names** (`text_gradient.py`) = importable Python modules
- **Hyphenated names** (`text-gradient.py`) = thin CLI wrappers (5-8 lines, delegate to underscore module)
- **scoring/** modules = one file per scoring dimension

## Security

- Use `shared.validate_command_safety()` before executing any user-supplied commands
- Use `shared.validate_regex_complexity()` before any user-supplied regex
- Use `shared.read_skill_safe()` for all file reads (enforces 1MB size limit)
- Never execute commands from eval-suite content without validation

## PR Checklist

- [ ] All tests pass (`make test-all`)
- [ ] Score is >= 90 (`make score`)
- [ ] New functions have docstrings and type hints
- [ ] Security functions used where applicable
- [ ] No hardcoded file paths
- [ ] CHANGELOG.md updated (if user-facing change)
