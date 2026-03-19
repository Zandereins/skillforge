# Contributing to SkillForge

Thanks for your interest in improving SkillForge.

## How to Contribute

### Report Issues
Open an issue if you find a bug, have a feature request, or want to share
results from using SkillForge on your own skills.

### Submit Improvements

1. Fork the repo
2. Create a branch: `git checkout -b feature/your-feature`
3. Make changes
4. Test: run `bash scripts/analyze-skill.sh` on the SkillForge skill itself
5. Open a PR with a clear description

### High-Impact Areas

- **New assertion types** for eval suites (regex, semantic, file-diff)
- **Domain-specific scoring rubrics** (e.g., API skills, doc skills, deploy skills)
- **Real-world benchmarks** — share before/after data from SkillForge runs
- **Scoring improvements** — better heuristics in `score-skill.py`
- **New subcommands** — e.g., `/skillforge:diff` to compare two skill versions
### Skill Quality Standards

When modifying the SkillForge skill itself, ensure:

- SKILL.md stays under 500 lines
- All referenced files exist
- Scripts are executable and produce valid output
- Examples use realistic, non-trivial scenarios
- Imperative voice throughout

### Code Style

- **Bash scripts**: `set -euo pipefail`, output JSON to stdout
- **Python**: Type hints, docstrings, argparse for CLI
- **Markdown**: ATX headers (`##`), fenced code blocks, consistent spacing

## License

By contributing, you agree that your contributions will be licensed under
the MIT License.
