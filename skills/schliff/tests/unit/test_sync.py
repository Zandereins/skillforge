"""Tests for schliff sync module — cross-file instruction analysis."""
import os

import pytest

from pathlib import Path

import sync
from sync import (
    discover_all_instruction_files,
    extract_directives,
    load_all_directives,
    group_directives_by_file,
    find_contradictions,
    find_gaps,
    find_redundancies,
    compute_consistency_score,
    format_sync_report,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_file(tmp_path, relative_path, content=""):
    """Create a file at relative_path inside tmp_path."""
    full = tmp_path / relative_path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content, encoding="utf-8")
    return full


def _directives_file(path, fmt, directives):
    """Build the dict structure expected by analysis functions."""
    return {"path": str(path), "format": fmt, "directives": directives}


# ===========================================================================
# Discovery tests
# ===========================================================================

class TestDiscovery:

    def test_discover_finds_all_formats(self, tmp_path):
        """All four instruction file formats are discovered."""
        _make_file(tmp_path, "SKILL.md", "# Skill")
        _make_file(tmp_path, "CLAUDE.md", "# Claude")
        _make_file(tmp_path, ".cursorrules", "rule: yes")
        _make_file(tmp_path, "AGENTS.md", "# Agents")

        results = discover_all_instruction_files(str(tmp_path))
        found_names = {os.path.basename(r["path"]) for r in results}

        assert "SKILL.md" in found_names
        assert "CLAUDE.md" in found_names
        assert ".cursorrules" in found_names
        assert "AGENTS.md" in found_names
        assert len(results) == 4

    def test_discover_excludes_git_and_node_modules(self, tmp_path):
        """Instruction files inside .git/ and node_modules/ are excluded."""
        _make_file(tmp_path, ".git/SKILL.md", "# hidden")
        _make_file(tmp_path, "node_modules/lib/SKILL.md", "# dep")
        _make_file(tmp_path, "src/SKILL.md", "# real")

        results = discover_all_instruction_files(str(tmp_path))
        paths = [r["path"] for r in results]

        assert any("src" in p for p in paths)
        assert not any(".git" in p for p in paths)
        assert not any("node_modules" in p for p in paths)

    def test_discover_empty_directory(self, tmp_path):
        """Empty directory returns an empty list."""
        results = discover_all_instruction_files(str(tmp_path))
        assert results == []

    def test_discover_nested_files(self, tmp_path):
        """Files in subdirectories are found with correct relative_path."""
        _make_file(tmp_path, "a/b/SKILL.md", "# nested")
        _make_file(tmp_path, "c/CLAUDE.md", "# also nested")

        results = discover_all_instruction_files(str(tmp_path))
        assert len(results) == 2

        rel_paths = {r["relative_path"] for r in results}
        assert any("a/b/SKILL.md" in rp or "a\\b\\SKILL.md" in rp for rp in rel_paths)
        assert any("c/CLAUDE.md" in rp or "c\\CLAUDE.md" in rp for rp in rel_paths)


# ===========================================================================
# Extraction tests
# ===========================================================================

class TestExtraction:

    def test_extract_always_directive(self):
        """'Always run linter before commit' → positive polarity, verb='run'."""
        content = "Always run linter before commit."
        directives = extract_directives(content)

        assert len(directives) >= 1
        d = directives[0]
        assert d["polarity"] == "positive"
        assert "run" in d["verb"].lower()
        assert "linter" in d["text"].lower()

    def test_extract_never_directive(self):
        """'Never push directly to main' → negative polarity."""
        content = "Never push directly to main."
        directives = extract_directives(content)

        assert len(directives) >= 1
        d = directives[0]
        assert d["polarity"] == "negative"
        assert "push" in d["text"].lower()

    def test_extract_config_directive(self):
        """'indent_size = 2' → config polarity with key/value."""
        content = "indent_size = 2"
        directives = extract_directives(content)

        assert len(directives) >= 1
        d = directives[0]
        assert d["polarity"] == "config"
        assert d["config_key"] == "indent_size"
        assert d["config_value"] == "2"

    def test_extract_ignores_code_blocks(self):
        """Directives inside fenced code blocks are NOT extracted."""
        content = (
            "Some preamble.\n"
            "\n"
            "```bash\n"
            "Always run tests first\n"
            "```\n"
            "\n"
            "Some postamble.\n"
        )
        directives = extract_directives(content)
        texts = [d["text"].lower() for d in directives]
        assert not any("always run tests" in t for t in texts)


# ===========================================================================
# Contradiction tests
# ===========================================================================

class TestContradictions:

    def test_contradictions_polarity_conflict(self):
        """Opposite polarity on same object → polarity contradiction."""
        files = [
            _directives_file("a.md", "skill", [
                {"text": "Always use tabs", "verb": "use", "object": "tabs",
                 "polarity": "positive", "line": 1},
            ]),
            _directives_file("b.md", "claude", [
                {"text": "Never use tabs", "verb": "use", "object": "tabs",
                 "polarity": "negative", "line": 1},
            ]),
        ]
        contradictions = find_contradictions(files)

        assert len(contradictions) >= 1
        types = {c["type"] for c in contradictions}
        assert "polarity" in types

    def test_contradictions_config_conflict(self):
        """Same config key with different values → config contradiction."""
        files = [
            _directives_file("a.md", "skill", [
                {"text": "indent_size = 2", "verb": "set", "object": "indent_size",
                 "polarity": "config", "line": 1,
                 "config_key": "indent_size", "config_value": "2"},
            ]),
            _directives_file("b.md", "claude", [
                {"text": "indent_size = 4", "verb": "set", "object": "indent_size",
                 "polarity": "config", "line": 1,
                 "config_key": "indent_size", "config_value": "4"},
            ]),
        ]
        contradictions = find_contradictions(files)

        assert len(contradictions) >= 1
        types = {c["type"] for c in contradictions}
        assert "config" in types

    def test_contradictions_semantic_opposition(self):
        """File A mentions 'tabs', file B mentions 'spaces' → semantic contradiction."""
        files = [
            _directives_file("a.md", "skill", [
                {"text": "Always use tabs for indentation", "verb": "use",
                 "object": "tabs", "polarity": "positive", "line": 1},
            ]),
            _directives_file("b.md", "claude", [
                {"text": "Always use spaces for indentation", "verb": "use",
                 "object": "spaces", "polarity": "positive", "line": 1},
            ]),
        ]
        contradictions = find_contradictions(files)

        assert len(contradictions) >= 1
        types = {c["type"] for c in contradictions}
        assert "semantic" in types


# ===========================================================================
# Consistency tests
# ===========================================================================

class TestConsistency:

    def test_no_contradictions_in_consistent_files(self):
        """Compatible directives across files → zero contradictions."""
        files = [
            _directives_file("a.md", "skill", [
                {"text": "Always run tests", "verb": "run", "object": "tests",
                 "polarity": "positive", "line": 1},
            ]),
            _directives_file("b.md", "claude", [
                {"text": "Always run linter", "verb": "run", "object": "linter",
                 "polarity": "positive", "line": 1},
            ]),
        ]
        contradictions = find_contradictions(files)
        assert contradictions == []

    def test_score_calculation(self):
        """Score formula: 100 - contradiction_penalty - gaps*5 - redundancies*3.

        high severity = -15, medium severity = -7.
        """
        # 2 high contradictions, 3 gaps, 1 redundancy → 100 - 30 - 15 - 3 = 52
        contradictions = [
            {"type": "polarity", "severity": "high"},
            {"type": "config", "severity": "high"},
        ]
        gaps = [{"topic": "a"}, {"topic": "b"}, {"topic": "c"}]
        redundancies = [{"directive": "x"}]

        score = compute_consistency_score(contradictions, gaps, redundancies)
        assert score == 52

    def test_score_medium_severity_weighted(self):
        """Medium-severity contradictions cost 7 points, not 15."""
        contradictions = [{"type": "semantic", "severity": "medium"}]
        score = compute_consistency_score(contradictions, [], [])
        assert score == 93  # 100 - 7

    def test_score_clamped_to_zero(self):
        """Score never drops below 0 even with many issues."""
        contradictions = [{"type": "polarity", "severity": "high"}] * 10  # -150
        gaps = [{"topic": "a"}] * 10  # -50
        redundancies = [{"directive": "x"}] * 10  # -30

        score = compute_consistency_score(contradictions, gaps, redundancies)
        assert score == 0

    def test_score_perfect(self):
        """No issues → score is 100."""
        score = compute_consistency_score([], [], [])
        assert score == 100


# ===========================================================================
# Gaps & redundancy tests
# ===========================================================================

class TestGapsAndRedundancies:

    def test_gaps_detect_missing_topics(self):
        """File A has 'test' topic, file B doesn't → gap detected."""
        files = [
            _directives_file("a.md", "skill", [
                {"text": "Always run tests", "verb": "run", "object": "tests",
                 "polarity": "positive", "line": 1},
                {"text": "Always use linter", "verb": "use", "object": "linter",
                 "polarity": "positive", "line": 2},
            ]),
            _directives_file("b.md", "claude", [
                {"text": "Always use linter", "verb": "use", "object": "linter",
                 "polarity": "positive", "line": 1},
            ]),
        ]
        gaps = find_gaps(files)

        assert len(gaps) >= 1
        topics = [g["topic"] for g in gaps]
        assert any("test" in t.lower() for t in topics)

    def test_redundancies_detected(self):
        """Same directive text in two files → redundancy found."""
        files = [
            _directives_file("a.md", "skill", [
                {"text": "Always run tests before commit", "verb": "run",
                 "object": "tests", "polarity": "positive", "line": 1},
            ]),
            _directives_file("b.md", "claude", [
                {"text": "Always run tests before commit", "verb": "run",
                 "object": "tests", "polarity": "positive", "line": 1},
            ]),
        ]
        redundancies = find_redundancies(files)

        assert len(redundancies) >= 1
        r = redundancies[0]
        assert len(r["found_in"]) >= 2
        assert r["similarity"] >= 0.9


# ===========================================================================
# Report test
# ===========================================================================

class TestReport:

    def test_report_format(self):
        """Report contains key sections: Files, Score, Contradictions, Gaps."""
        contradictions = [
            {"type": "polarity", "file_a": "a.md", "file_b": "b.md",
             "directive_a": "Always use tabs", "directive_b": "Never use tabs",
             "severity": "high"},
        ]
        gaps = [{"topic": "testing", "present_in": ["a.md"], "missing_from": ["b.md"]}]
        redundancies = []
        score = 80
        files = [
            _directives_file("a.md", "skill", []),
            _directives_file("b.md", "claude", []),
        ]

        report = format_sync_report(contradictions, gaps, redundancies, score, files)

        assert isinstance(report, str)
        assert len(report) > 0
        # Key sections present (case-insensitive check)
        report_lower = report.lower()
        assert "file" in report_lower
        assert "score" in report_lower or "80" in report
        assert "contradiction" in report_lower
        assert "gap" in report_lower


# ===========================================================================
# Additional coverage tests (added by audit)
# ===========================================================================

class TestExtractionAdditional:

    def test_extract_prefer_directive(self):
        """'Prefer composition over inheritance' → preference polarity."""
        directives = extract_directives("Prefer composition over inheritance.")
        assert any(d["polarity"] == "preference" for d in directives)

    def test_extract_avoid_directive(self):
        """'Avoid global mutable state' → avoidance polarity."""
        directives = extract_directives("Avoid global mutable state.")
        assert any(d["polarity"] == "avoidance" for d in directives)

    def test_extract_must_not_directive(self):
        """'Must not commit secrets' → negative polarity."""
        directives = extract_directives("Must not commit secrets to the repo.")
        assert any(d["polarity"] == "negative" for d in directives)

    def test_extract_use_directive(self):
        """'Use TypeScript for all modules' → positive polarity with verb 'use'."""
        directives = extract_directives("Use TypeScript for all new modules.")
        assert any(d["polarity"] == "positive" and d["verb"] == "use"
                    for d in directives)


class TestLoadAllDirectives:

    def test_end_to_end(self, tmp_path, monkeypatch):
        """load_all_directives discovers files and extracts directives."""
        (tmp_path / "SKILL.md").write_text(
            "Always run tests before merging.", encoding="utf-8")
        (tmp_path / "CLAUDE.md").write_text(
            "indent_size = 4", encoding="utf-8")

        monkeypatch.setattr(
            sync, "read_skill_safe",
            lambda p: Path(p).read_text(encoding="utf-8"))

        results = load_all_directives(str(tmp_path))
        assert len(results) >= 2
        assert all("file" in r and "directive" in r for r in results)

    def test_skips_unreadable(self, tmp_path, monkeypatch):
        """Files that raise on read are silently skipped."""
        (tmp_path / "SKILL.md").write_text("Always run tests.", encoding="utf-8")

        def _failing_read(path):
            raise OSError("permission denied")
        monkeypatch.setattr(sync, "read_skill_safe", _failing_read)

        results = load_all_directives(str(tmp_path))
        assert results == []


class TestEdgeCases:

    def test_gaps_single_file_returns_empty(self):
        """Single file cannot have gaps."""
        files = [_directives_file("a.md", "skill", [
            {"text": "Always run tests", "verb": "run", "object": "tests",
             "polarity": "positive", "line": 1},
        ])]
        assert find_gaps(files) == []

    def test_redundancies_none_found(self):
        """Completely different directives → no redundancies."""
        files = [
            _directives_file("a.md", "skill", [
                {"text": "Always run tests", "verb": "run", "object": "tests",
                 "polarity": "positive", "line": 1},
            ]),
            _directives_file("b.md", "claude", [
                {"text": "Deploy to staging first", "verb": "deploy",
                 "object": "staging", "polarity": "positive", "line": 1},
            ]),
        ]
        assert find_redundancies(files) == []

    def test_semantic_opposition_reverse_direction(self):
        """File A mentions 'spaces', file B mentions 'tabs' → still detected."""
        files = [
            _directives_file("a.md", "skill", [
                {"text": "Always use spaces for indentation", "verb": "use",
                 "object": "spaces", "polarity": "positive", "line": 1},
            ]),
            _directives_file("b.md", "claude", [
                {"text": "Always use tabs for indentation", "verb": "use",
                 "object": "tabs", "polarity": "positive", "line": 1},
            ]),
        ]
        contradictions = find_contradictions(files)
        assert any(c["type"] == "semantic" for c in contradictions)


# ===========================================================================
# Mutation-catching tests (added by audit iteration 2)
# ===========================================================================

class TestMutationCatching:

    def test_extract_single_directive_no_duplicates(self):
        """A single imperative sentence must produce exactly one directive."""
        directives = extract_directives("Always run linter before commit.")
        assert len(directives) == 1

    def test_contradictions_exact_count_polarity(self):
        """Exactly one polarity contradiction for one conflicting pair."""
        files = [
            _directives_file("a.md", "skill", [
                {"text": "Always use tabs", "verb": "use", "object": "tabs",
                 "polarity": "positive", "line": 1},
            ]),
            _directives_file("b.md", "claude", [
                {"text": "Never use tabs", "verb": "use", "object": "tabs",
                 "polarity": "negative", "line": 1},
            ]),
        ]
        polarity_hits = [c for c in find_contradictions(files)
                         if c["type"] == "polarity"]
        assert len(polarity_hits) == 1

    def test_discover_results_sorted(self, tmp_path):
        """Results must be sorted by relative_path."""
        _make_file(tmp_path, "z/SKILL.md", "# z")
        _make_file(tmp_path, "a/SKILL.md", "# a")
        _make_file(tmp_path, "m/CLAUDE.md", "# m")

        results = discover_all_instruction_files(str(tmp_path))
        rel_paths = [r["relative_path"] for r in results]
        assert rel_paths == sorted(rel_paths)

    def test_code_block_with_inline_backticks(self):
        """Code blocks containing inline backticks must still be stripped."""
        content = (
            "Some preamble.\n\n"
            "```python\n"
            "x = f\"use `name` here\"\n"
            "Always run tests\n"
            "```\n\n"
            "Some postamble.\n"
        )
        directives = extract_directives(content)
        texts = [d["text"].lower() for d in directives]
        assert not any("always run tests" in t for t in texts)


class TestGroupDirectives:

    def test_groups_by_file(self):
        """Flat directives are grouped into per-file dicts."""
        flat = [
            {"file": "CLAUDE.md", "format": "claude.md",
             "directive": {"text": "Always run tests", "verb": "run",
                          "object": "tests", "polarity": "positive", "line": 1}},
            {"file": "CLAUDE.md", "format": "claude.md",
             "directive": {"text": "Never skip linting", "verb": "skip",
                          "object": "linting", "polarity": "negative", "line": 2}},
            {"file": "SKILL.md", "format": "skill.md",
             "directive": {"text": "Use TypeScript", "verb": "use",
                          "object": "TypeScript", "polarity": "positive", "line": 1}},
        ]
        grouped = group_directives_by_file(flat)
        assert len(grouped) == 2

        claude = next(g for g in grouped if g["path"] == "CLAUDE.md")
        assert len(claude["directives"]) == 2
        assert claude["format"] == "claude.md"

        skill = next(g for g in grouped if g["path"] == "SKILL.md")
        assert len(skill["directives"]) == 1

    def test_empty_input(self):
        """Empty flat list returns empty grouped list."""
        assert group_directives_by_file([]) == []
