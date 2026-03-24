"""Unit tests for the anti-gaming benchmark runner."""
import json
import sys
from pathlib import Path

import pytest

# Add scripts dir to path for scoring imports
_SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent.parent / "skills" / "schliff" / "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

# Add benchmark dir for run module
_BENCH_DIR = str(Path(__file__).resolve().parent)
if _BENCH_DIR not in sys.path:
    sys.path.insert(0, _BENCH_DIR)

import run as bench_run


# ---------------------------------------------------------------------------
# Skill files exist
# ---------------------------------------------------------------------------

class TestBenchmarkFiles:
    def test_all_skill_files_exist(self):
        for b in bench_run.BENCHMARKS:
            path = bench_run._SKILLS_DIR / b["file"]
            assert path.exists(), f"Missing benchmark skill: {b['file']}"

    def test_all_skills_have_frontmatter(self):
        for b in bench_run.BENCHMARKS:
            path = bench_run._SKILLS_DIR / b["file"]
            content = path.read_text(encoding="utf-8")
            assert content.startswith("---"), f"{b['file']} missing frontmatter"
            # Must have closing ---
            assert content.count("---") >= 2, f"{b['file']} incomplete frontmatter"

    def test_all_skills_have_name_field(self):
        for b in bench_run.BENCHMARKS:
            path = bench_run._SKILLS_DIR / b["file"]
            content = path.read_text(encoding="utf-8")
            assert "name:" in content, f"{b['file']} missing name field"


# ---------------------------------------------------------------------------
# Benchmark metadata
# ---------------------------------------------------------------------------

class TestBenchmarkMetadata:
    def test_six_benchmarks_defined(self):
        assert len(bench_run.BENCHMARKS) == 6

    def test_each_has_required_keys(self):
        required = {"file", "target_dimension", "gaming_vector", "detection"}
        for b in bench_run.BENCHMARKS:
            assert required.issubset(b.keys()), f"Missing keys in {b['file']}"

    def test_target_dimensions_are_valid(self):
        valid = {"structure", "triggers", "quality", "edges",
                 "efficiency", "composability", "clarity"}
        for b in bench_run.BENCHMARKS:
            assert b["target_dimension"] in valid, (
                f"Invalid dimension {b['target_dimension']} in {b['file']}"
            )


# ---------------------------------------------------------------------------
# score_skill
# ---------------------------------------------------------------------------

class TestScoreSkill:
    def test_returns_composite(self):
        path = str(bench_run._SKILLS_DIR / "no-scope.md")
        result = bench_run.score_skill(path)
        assert "composite" in result
        assert isinstance(result["composite"], float)

    def test_returns_all_dimensions(self):
        path = str(bench_run._SKILLS_DIR / "no-scope.md")
        result = bench_run.score_skill(path)
        assert "scores" in result
        assert "structure" in result["scores"]
        assert "composability" in result["scores"]


# ---------------------------------------------------------------------------
# run_benchmarks
# ---------------------------------------------------------------------------

class TestRunBenchmarks:
    def test_returns_list(self):
        results = bench_run.run_benchmarks()
        assert isinstance(results, list)
        assert len(results) == 6

    def test_each_result_has_caught_field(self):
        results = bench_run.run_benchmarks()
        for r in results:
            assert "caught" in r

    def test_each_result_has_target_score(self):
        results = bench_run.run_benchmarks()
        for r in results:
            assert "target_score" in r
            assert isinstance(r["target_score"], (int, float))

    def test_no_scope_caught(self):
        """Composability should catch missing scope boundaries."""
        results = bench_run.run_benchmarks()
        no_scope = [r for r in results if r["file"] == "no-scope.md"][0]
        assert no_scope["caught"] is True
        assert no_scope["target_score"] < 50

    def test_contradiction_caught(self):
        """Clarity should catch contradictory instructions."""
        results = bench_run.run_benchmarks()
        contradiction = [r for r in results if r["file"] == "contradiction-skill.md"][0]
        assert contradiction["caught"] is True
        assert "contradictions" in str(contradiction["target_issues"])

    def test_bloated_preamble_caught(self):
        """Efficiency should catch low signal-to-noise ratio."""
        results = bench_run.run_benchmarks()
        bloated = [r for r in results if r["file"] == "bloated-preamble.md"][0]
        assert bloated["caught"] is True
        assert bloated["target_score"] < 80

    def test_inflated_headers_caught(self):
        """Structure should catch empty section headers."""
        results = bench_run.run_benchmarks()
        inflated = [r for r in results if r["file"] == "inflated-headers.md"][0]
        assert inflated["caught"] is True
        assert "empty_sections" in str(inflated["target_issues"])


# ---------------------------------------------------------------------------
# format_markdown
# ---------------------------------------------------------------------------

class TestFormatMarkdown:
    def test_contains_header(self):
        results = bench_run.run_benchmarks()
        md = bench_run.format_markdown(results)
        assert "# Anti-Gaming Benchmark" in md

    def test_contains_summary_table(self):
        results = bench_run.run_benchmarks()
        md = bench_run.format_markdown(results)
        assert "| Skill |" in md
        assert "| no-scope.md" in md

    def test_contains_detail_sections(self):
        results = bench_run.run_benchmarks()
        md = bench_run.format_markdown(results)
        assert "## Detail" in md
        assert "### no-scope.md" in md

    def test_json_serializable(self):
        results = bench_run.run_benchmarks()
        # Filter like main() does
        output = []
        for r in results:
            entry = {k: v for k, v in r.items() if k != "target_details"}
            output.append(entry)
        serialized = json.dumps(output)
        assert isinstance(serialized, str)
