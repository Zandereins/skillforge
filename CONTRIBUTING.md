# Contributing to SkillForge

Thanks for your interest in improving SkillForge.

## Getting Started

```bash
git clone https://github.com/Zandereins/skillforge.git
cd skillforge/skills/skillforge

# Run the test suite
bash scripts/test-integration.sh
bash scripts/test-self.sh

# Score the skill
python3 scripts/score-skill.py SKILL.md --json
```

## How to Contribute

### Report Issues

Open an issue if you find a bug, have a feature request, or want to share
results from using SkillForge on your own skills.

### Submit Improvements

1. Fork the repo
2. Create a branch: `git checkout -b feature/your-feature`
3. Make changes
4. Run the full test suite:
   ```bash
   cd skills/skillforge
   bash scripts/test-integration.sh   # Must pass all tests
   bash scripts/test-self.sh          # Must pass all tests
   python3 scripts/score-skill.py SKILL.md --json  # Composite must be >= 90
   ```
5. Open a PR with a clear description

### PR Checklist

- [ ] All integration tests pass (`bash scripts/test-integration.sh`)
- [ ] All self-tests pass (`bash scripts/test-self.sh`)
- [ ] Composite score >= 90 (`python3 scripts/score-skill.py SKILL.md --json`)
- [ ] SKILL.md stays under 500 lines
- [ ] All referenced files exist
- [ ] New tests added for new functionality
- [ ] CHANGELOG.md updated

## High-Impact Areas

- **New assertion types** — regex, semantic, file-diff for eval suites
- **Scoring improvements** — better heuristics in `score-skill.py`
- **Domain-specific rubrics** — API skills, doc skills, deploy skills
- **Real-world benchmarks** — share before/after data from SkillForge runs
- **New subcommands** — e.g., `/skillforge:diff` to compare two skill versions

## Adding a New Metric

1. Add a `score_<metric>()` function to `scripts/score-skill.py`
2. Return `{"score": 0-100, "issues": [...], "details": {...}}`
3. Add the metric to `compute_composite()` weights
4. Add tests in `scripts/test-integration.sh`
5. Document in `references/metrics-catalog.md`

## Code Style

- **Bash scripts**: `set -euo pipefail`, JSON output to stdout, errors to stderr
- **Python**: Type hints, docstrings, argparse for CLI, `max(0, min(100, score))` for capping
- **Markdown**: ATX headers (`##`), fenced code blocks, imperative voice

## Skill Quality Standards

When modifying the SkillForge skill itself:

- SKILL.md stays under 500 lines
- All referenced files exist
- Scripts are executable and produce valid output
- Examples use realistic, non-trivial scenarios
- Imperative voice throughout

## License

By contributing, you agree that your contributions will be licensed under
the MIT License.
