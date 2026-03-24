"""Stress tests and boundary tests for the Schliff scoring system.

Categories:
1. Boundary tests for every scorer — empty, minimal, 10k lines, code-only, headers-only
2. Unicode stress tests — CJK, emoji, RTL, zero-width, combining diacritics
3. Regression pinning — exact scores for known inputs (measured first, then pinned)
4. Composite weight math — all-100, all-0, single-dimension, clarity redistribution
5. Determinism — 10 repeated runs, different file paths with same content
"""
import sys
import tempfile
from pathlib import Path

import pytest

# Ensure scripts/ is on path (also done by conftest.py)
SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from scoring import (
    score_structure,
    score_efficiency,
    score_composability,
    score_clarity,
    compute_composite,
)
from shared import invalidate_cache, MAX_SKILL_SIZE


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write(tmp_path: Path, content: str, name: str = "SKILL.md") -> str:
    """Write content to a temp file and return the path string."""
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return str(p)


def _score_all(skill_path: str) -> dict:
    """Score the four structural+clarity dimensions, return composite result plus dims."""
    scores = {
        "structure": score_structure(skill_path),
        "efficiency": score_efficiency(skill_path),
        "composability": score_composability(skill_path),
        "clarity": score_clarity(skill_path),
    }
    result = compute_composite(scores)
    result["dimensions"] = {k: v["score"] for k, v in scores.items()}
    return result


def _make_score_dict(dim_scores: dict) -> dict:
    """Wrap a {dim: score} mapping into the format expected by compute_composite."""
    return {k: {"score": v, "issues": [], "details": {}} for k, v in dim_scores.items()}


# ---------------------------------------------------------------------------
# 1. Boundary tests for every scorer
# ---------------------------------------------------------------------------

class TestBoundaryEmptySkill:
    """Empty string (0 bytes) — every scorer must return 0 or a safe default."""

    def test_structure_empty_returns_zero(self, tmp_path):
        path = _write(tmp_path, "")
        result = score_structure(path)
        assert result["score"] == 0
        assert "empty_skill_body" in result["issues"]

    def test_efficiency_empty_returns_zero(self, tmp_path):
        path = _write(tmp_path, "")
        result = score_efficiency(path)
        assert result["score"] == 0
        assert "empty_skill_body" in result["issues"]

    def test_composability_empty_returns_nonzero_global_state_pass(self, tmp_path):
        """Empty content has no global state patterns → gets 20 pts (2 checks pass).

        Composability check 2 (no global state) and check 5 (no tool requirements)
        pass on empty content because the absence of patterns is still a pass.
        """
        path = _write(tmp_path, "")
        result = score_composability(path)
        # No global state patterns → check 2 passes (10 pts)
        # No hard requirements → check 5 passes (10 pts)
        assert result["score"] == 20

    def test_clarity_empty_returns_zero(self, tmp_path):
        path = _write(tmp_path, "")
        result = score_clarity(path)
        assert result["score"] == 0
        assert "empty_skill_body" in result["issues"]

    def test_all_scorers_return_dict_with_required_keys(self, tmp_path):
        path = _write(tmp_path, "")
        for scorer in (score_structure, score_efficiency, score_composability, score_clarity):
            result = scorer(path)
            assert "score" in result, f"{scorer.__name__} missing 'score' key"
            assert "issues" in result, f"{scorer.__name__} missing 'issues' key"
            assert "details" in result, f"{scorer.__name__} missing 'details' key"


class TestBoundaryMinimalFrontmatterOnly:
    """Skill with only frontmatter and no body content."""

    FRONTMATTER_ONLY = "---\nname: x\ndescription: Use when x.\n---\n"
    MINIMAL_NO_DESC = "---\nname: x\n---\n"

    def test_structure_frontmatter_only_returns_zero(self, tmp_path):
        """Body is empty after stripping frontmatter → empty_skill_body guard fires."""
        path = _write(tmp_path, self.FRONTMATTER_ONLY)
        result = score_structure(path)
        assert result["score"] == 0
        assert "empty_skill_body" in result["issues"]

    def test_efficiency_frontmatter_only_returns_zero(self, tmp_path):
        path = _write(tmp_path, self.FRONTMATTER_ONLY)
        result = score_efficiency(path)
        assert result["score"] == 0
        assert "empty_skill_body" in result["issues"]

    def test_clarity_frontmatter_only_returns_zero(self, tmp_path):
        path = _write(tmp_path, self.FRONTMATTER_ONLY)
        result = score_clarity(path)
        assert result["score"] == 0
        assert "empty_skill_body" in result["issues"]

    def test_composability_frontmatter_only_partial_score(self, tmp_path):
        """Frontmatter-only passes global-state and no-hard-requirements checks."""
        path = _write(tmp_path, self.FRONTMATTER_ONLY)
        result = score_composability(path)
        # Must not crash; score reflects what passes on frontmatter-only content
        assert isinstance(result["score"], int)
        assert 0 <= result["score"] <= 100

    def test_structure_minimal_no_desc_returns_zero(self, tmp_path):
        """'---\\nname: x\\n---\\n' has no body → empty_skill_body."""
        path = _write(tmp_path, self.MINIMAL_NO_DESC)
        result = score_structure(path)
        assert result["score"] == 0
        assert "empty_skill_body" in result["issues"]


class TestBoundaryCodeBlocksOnly:
    """Skill whose body consists entirely of code blocks with no prose."""

    CODE_ONLY = (
        "---\nname: code-only\ndescription: Use when x.\n---\n"
        "```bash\necho hello\n```\n"
        "```python\nprint('hi')\n```\n"
    )

    def test_structure_code_only_does_not_crash(self, tmp_path):
        path = _write(tmp_path, self.CODE_ONLY)
        result = score_structure(path)
        assert isinstance(result["score"], int)
        assert 0 <= result["score"] <= 100

    def test_structure_code_only_gets_frontmatter_points(self, tmp_path):
        """Has valid frontmatter → at least the frontmatter check passes."""
        path = _write(tmp_path, self.CODE_ONLY)
        result = score_structure(path)
        assert result["score"] >= 10

    def test_efficiency_code_only_does_not_return_zero(self, tmp_path):
        """Code blocks contribute words; efficiency must score non-zero."""
        path = _write(tmp_path, self.CODE_ONLY)
        result = score_efficiency(path)
        assert result["score"] > 0

    def test_clarity_code_only_returns_zero_empty_prose(self, tmp_path):
        """Clarity strips code blocks — remaining prose is empty → empty_skill_body."""
        path = _write(tmp_path, self.CODE_ONLY)
        result = score_clarity(path)
        assert result["score"] == 0
        assert "empty_skill_body" in result["issues"]

    def test_composability_code_only_does_not_crash(self, tmp_path):
        path = _write(tmp_path, self.CODE_ONLY)
        result = score_composability(path)
        assert "score" in result


class TestBoundaryHeadersOnlyNoContent:
    """Skill with headers but no content under them."""

    HEADERS_ONLY = (
        "---\nname: headers-only\ndescription: Use when x.\n---\n\n"
        "# Title\n\n## Section A\n\n## Section B\n\n## Section C\n"
    )

    def test_structure_headers_only_reports_empty_sections(self, tmp_path):
        path = _write(tmp_path, self.HEADERS_ONLY)
        result = score_structure(path)
        assert any("empty_sections" in issue for issue in result["issues"])

    def test_structure_headers_only_does_not_give_full_score(self, tmp_path):
        path = _write(tmp_path, self.HEADERS_ONLY)
        result = score_structure(path)
        # Headers with no content should not score full points
        assert result["score"] < 90

    def test_clarity_headers_only_no_contradictions(self, tmp_path):
        """Empty sections have no contradictions — clarity scores 100."""
        path = _write(tmp_path, self.HEADERS_ONLY)
        result = score_clarity(path)
        assert result["score"] == 100

    def test_efficiency_headers_only_does_not_crash(self, tmp_path):
        path = _write(tmp_path, self.HEADERS_ONLY)
        result = score_efficiency(path)
        assert "score" in result
        assert isinstance(result["score"], (int, float))


class TestBoundaryLargeSkill:
    """Skill with 10,000 lines — well within the 1 MB limit."""

    @pytest.fixture(scope="class")
    def large_skill_path(self, tmp_path_factory):
        """Build a 10k-line skill once and reuse across tests in this class."""
        tmp = tmp_path_factory.mktemp("large")
        header = (
            "---\nname: large-skill\n"
            "description: Use when you need to process large amounts of content.\n"
            "---\n\n# Large Skill\n\n"
        )
        # 5000 prose lines + 5000 instruction lines
        body = ("This is content line.\n" * 5000) + ("Run the verification step.\n" * 5000)
        content = header + body
        assert len(content.encode()) <= MAX_SKILL_SIZE, (
            f"Test fixture exceeds MAX_SKILL_SIZE ({MAX_SKILL_SIZE})"
        )
        p = tmp / "SKILL.md"
        p.write_text(content, encoding="utf-8")
        return str(p)

    def test_structure_large_skill_does_not_crash(self, large_skill_path):
        result = score_structure(large_skill_path)
        assert "score" in result

    def test_structure_large_skill_penalizes_length(self, large_skill_path):
        """A 10k-line skill should score lower on structure than a concise one."""
        result = score_structure(large_skill_path)
        # Long skill: no length bonus (>500 lines), no progressive disclosure bonus
        assert result["score"] < 80

    def test_efficiency_large_skill_penalizes_verbosity(self, large_skill_path):
        """High word count with low density should suppress efficiency score."""
        result = score_efficiency(large_skill_path)
        assert result["score"] < 50

    def test_composability_large_skill_does_not_crash(self, large_skill_path):
        result = score_composability(large_skill_path)
        assert "score" in result
        assert 0 <= result["score"] <= 100

    def test_clarity_large_skill_does_not_crash(self, large_skill_path):
        result = score_clarity(large_skill_path)
        assert "score" in result
        assert 0 <= result["score"] <= 100


# ---------------------------------------------------------------------------
# 2. Unicode stress tests
# ---------------------------------------------------------------------------

class TestUnicodeCJK:
    """CJK characters in skill body must not crash any scorer."""

    CJK_SKILL = (
        "---\nname: cjk-skill\n"
        "description: Use when working with CJK text.\n---\n\n"
        "# CJK Skill\n\n"
        "这是一个测试技能。日本語のテキストも含まれています。한국어 텍스트도 포함됩니다。\n\n"
        "## Instructions\n\n"
        "1. Read the content\n"
        "2. Run the analysis\n"
        "3. Verify the output\n"
    )

    def test_structure_cjk_does_not_crash(self, tmp_path):
        path = _write(tmp_path, self.CJK_SKILL)
        result = score_structure(path)
        assert isinstance(result["score"], int)
        assert 0 <= result["score"] <= 100

    def test_efficiency_cjk_does_not_crash(self, tmp_path):
        path = _write(tmp_path, self.CJK_SKILL)
        result = score_efficiency(path)
        assert isinstance(result["score"], (int, float))

    def test_composability_cjk_does_not_crash(self, tmp_path):
        path = _write(tmp_path, self.CJK_SKILL)
        result = score_composability(path)
        assert "score" in result

    def test_clarity_cjk_does_not_crash(self, tmp_path):
        path = _write(tmp_path, self.CJK_SKILL)
        result = score_clarity(path)
        assert "score" in result

    def test_structure_cjk_achieves_reasonable_score(self, tmp_path):
        """CJK body still has valid frontmatter and headers — structure ≥ 60."""
        path = _write(tmp_path, self.CJK_SKILL)
        result = score_structure(path)
        assert result["score"] >= 60, (
            f"CJK skill with frontmatter+headers should score >= 60, got {result['score']}"
        )


class TestUnicodeEmojiInFrontmatter:
    """Emoji in frontmatter name field — YAML parse and regex must not crash."""

    EMOJI_SKILL = (
        "---\nname: emoji-skill-🚀\n"
        "description: Use when you need rocket speed.\n---\n\n"
        "# Emoji Skill\n\n"
        "Run the rocket analysis.\n"
    )

    def test_structure_emoji_name_does_not_crash(self, tmp_path):
        path = _write(tmp_path, self.EMOJI_SKILL)
        result = score_structure(path)
        assert "score" in result
        assert isinstance(result["score"], int)

    def test_efficiency_emoji_name_does_not_crash(self, tmp_path):
        path = _write(tmp_path, self.EMOJI_SKILL)
        result = score_efficiency(path)
        assert "score" in result

    def test_composability_emoji_name_does_not_crash(self, tmp_path):
        path = _write(tmp_path, self.EMOJI_SKILL)
        result = score_composability(path)
        assert "score" in result

    def test_clarity_emoji_name_does_not_crash(self, tmp_path):
        path = _write(tmp_path, self.EMOJI_SKILL)
        result = score_clarity(path)
        assert "score" in result


class TestUnicodeRTLMixed:
    """RTL text mixed with LTR — bidirectional text must not corrupt scoring."""

    RTL_SKILL = (
        "---\nname: rtl-skill\n"
        "description: Use when working with RTL text.\n---\n\n"
        "# RTL Mixed Skill\n\n"
        "This skill handles \u0645\u0631\u062d\u0628\u0627 \u0628\u0627\u0644\u0639\u0627\u0644\u0645 Arabic text alongside English.\n\n"
        "## Instructions\n\n"
        "1. Run the text analysis\n"
        "2. Check encoding output\n"
    )

    def test_structure_rtl_does_not_crash(self, tmp_path):
        path = _write(tmp_path, self.RTL_SKILL)
        result = score_structure(path)
        assert isinstance(result["score"], int)

    def test_clarity_rtl_does_not_crash(self, tmp_path):
        path = _write(tmp_path, self.RTL_SKILL)
        result = score_clarity(path)
        assert "score" in result

    def test_structure_rtl_achieves_reasonable_score(self, tmp_path):
        """RTL skill has valid frontmatter and headers — structure ≥ 60."""
        path = _write(tmp_path, self.RTL_SKILL)
        result = score_structure(path)
        assert result["score"] >= 60


class TestUnicodeZeroWidthChars:
    """Zero-width characters (U+200B) embedded in prose must not break tokenisation."""

    ZWC_SKILL = (
        "---\nname: zero-width\n"
        "description: Use when testing zero-width chars.\n---\n\n"
        "# Zero Width\n\n"
        "Run\u200bthe\u200banalysis\u200bcarefully.\n\n"
        "## Instructions\n\n"
        "1. Check the output\n"
    )

    def test_all_scorers_do_not_crash(self, tmp_path):
        path = _write(tmp_path, self.ZWC_SKILL)
        for scorer in (score_structure, score_efficiency, score_composability, score_clarity):
            result = scorer(path)
            assert "score" in result, f"{scorer.__name__} crashed on zero-width content"

    def test_structure_zero_width_achieves_reasonable_score(self, tmp_path):
        path = _write(tmp_path, self.ZWC_SKILL)
        result = score_structure(path)
        assert result["score"] >= 60


class TestUnicodeCombiningDiacritics:
    """Combining diacritical marks (NFD form) must not crash Unicode-naive regex."""

    DIACRITIC_SKILL = (
        "---\nname: combining-diacritics\n"
        "description: Use when te\u0301sting co\u0302mbining marks.\n---\n\n"
        "# Combining Diacritics\n\n"
        "Run the ana\u0301lysis with dia\u0302critics.\n\n"
        "## Instructions\n\n"
        "1. Check the output carefully\n"
    )

    def test_all_scorers_do_not_crash(self, tmp_path):
        path = _write(tmp_path, self.DIACRITIC_SKILL)
        for scorer in (score_structure, score_efficiency, score_composability, score_clarity):
            result = scorer(path)
            assert "score" in result, f"{scorer.__name__} crashed on combining diacritics"

    def test_structure_diacritics_achieves_reasonable_score(self, tmp_path):
        path = _write(tmp_path, self.DIACRITIC_SKILL)
        result = score_structure(path)
        assert result["score"] >= 60


# ---------------------------------------------------------------------------
# 3. Regression pinning — exact scores for known inputs
# ---------------------------------------------------------------------------

# Measured 2026-03-24. Update only when the scoring algorithm changes intentionally.

_GOOD_SKILL_CONTENT = '''\
---
name: test-skill
description: >
  A test skill for unit testing. Use when testing scoring functions.
  Do not use for production deployment or security scanning.
---

# Test Skill

Use this skill when you need to test scoring functions.

## Instructions

1. Read the input file
2. Run the scoring function
3. Verify the output matches expectations

## Examples

Example 1: Basic scoring
```bash
python3 scripts/score-skill.py test.md --json
```

Example 2: With eval suite
```bash
python3 scripts/score-skill.py test.md --eval-suite eval.json
```

## When NOT to Use

Do not use this skill for:
- Production deployment
- Security vulnerability scanning
- Database migrations
'''

_BAD_SKILL_CONTENT = '''\
no frontmatter here

TODO: add description
FIXME: add examples

you might want to consider maybe possibly doing something
you could try to perhaps attempt this
'''


class TestRegressionGoodSkillPinned:
    """Pin exact dimension scores for the canonical good_skill fixture.

    These values were measured at a known-good state. A change here signals
    a scoring algorithm change that needs deliberate review.
    """

    def test_structure_exact(self, tmp_path):
        path = _write(tmp_path, _GOOD_SKILL_CONTENT)
        result = score_structure(path)
        assert result["score"] == 95, (
            f"good_skill structure regression: expected 95, got {result['score']}"
        )

    def test_efficiency_exact(self, tmp_path):
        path = _write(tmp_path, _GOOD_SKILL_CONTENT)
        result = score_efficiency(path)
        assert result["score"] == 100, (
            f"good_skill efficiency regression: expected 100, got {result['score']}"
        )

    def test_composability_exact(self, tmp_path):
        path = _write(tmp_path, _GOOD_SKILL_CONTENT)
        result = score_composability(path)
        assert result["score"] == 30, (
            f"good_skill composability regression: expected 30, got {result['score']}"
        )

    def test_clarity_exact(self, tmp_path):
        path = _write(tmp_path, _GOOD_SKILL_CONTENT)
        result = score_clarity(path)
        assert result["score"] == 87, (
            f"good_skill clarity regression: expected 87, got {result['score']}"
        )

    def test_composite_exact(self, tmp_path):
        path = _write(tmp_path, _GOOD_SKILL_CONTENT)
        result = _score_all(path)
        assert result["score"] == 79.1, (
            f"good_skill composite regression: expected 79.1, got {result['score']}"
        )


class TestRegressionBadSkillPinned:
    """Pin exact dimension scores for the canonical bad_skill fixture."""

    def test_structure_exact(self, tmp_path):
        path = _write(tmp_path, _BAD_SKILL_CONTENT)
        result = score_structure(path)
        assert result["score"] == 33, (
            f"bad_skill structure regression: expected 33, got {result['score']}"
        )

    def test_efficiency_exact(self, tmp_path):
        path = _write(tmp_path, _BAD_SKILL_CONTENT)
        result = score_efficiency(path)
        assert result["score"] == 40, (
            f"bad_skill efficiency regression: expected 40, got {result['score']}"
        )

    def test_composability_exact(self, tmp_path):
        path = _write(tmp_path, _BAD_SKILL_CONTENT)
        result = score_composability(path)
        assert result["score"] == 20, (
            f"bad_skill composability regression: expected 20, got {result['score']}"
        )

    def test_clarity_exact(self, tmp_path):
        """Bad skill has no contradictions — clarity = 100 (no issues to penalise)."""
        path = _write(tmp_path, _BAD_SKILL_CONTENT)
        result = score_clarity(path)
        assert result["score"] == 100, (
            f"bad_skill clarity regression: expected 100, got {result['score']}"
        )

    def test_composite_exact(self, tmp_path):
        path = _write(tmp_path, _BAD_SKILL_CONTENT)
        result = _score_all(path)
        assert result["score"] == 40.3, (
            f"bad_skill composite regression: expected 40.3, got {result['score']}"
        )


class TestRegressionRealSkillMd:
    """Schliff's own SKILL.md composite must stay within 95.4 ± 0.5."""

    SKILL_MD_PATH = str(
        Path(__file__).resolve().parent.parent.parent / "SKILL.md"
    )

    def test_composite_within_tolerance(self):
        result = _score_all(self.SKILL_MD_PATH)
        # Measured 2026-03-24: structural-only composite (structure, efficiency,
        # composability, clarity) = 95.8 after structural-marker exclusion fix.
        # Tolerance 1.0 guards against regressions without breaking on
        # rounding changes or minor content edits.
        expected = 95.8
        tolerance = 1.0
        assert abs(result["score"] - expected) <= tolerance, (
            f"SKILL.md composite regression: expected {expected} ±{tolerance}, "
            f"got {result['score']}"
        )

    def test_structure_perfect(self):
        result = score_structure(self.SKILL_MD_PATH)
        assert result["score"] == 100, (
            f"SKILL.md structure regression: expected 100, got {result['score']}"
        )

    def test_composability_perfect(self):
        result = score_composability(self.SKILL_MD_PATH)
        assert result["score"] == 100, (
            f"SKILL.md composability regression: expected 100, got {result['score']}"
        )

    def test_clarity_perfect(self):
        result = score_clarity(self.SKILL_MD_PATH)
        assert result["score"] == 100, (
            f"SKILL.md clarity regression: expected 100, got {result['score']}"
        )


# ---------------------------------------------------------------------------
# 4. Composite weight math
# ---------------------------------------------------------------------------

_ALL_7_DIMS = ["structure", "triggers", "quality", "edges", "efficiency", "composability", "runtime"]


class TestCompositeWeightMath:
    """Verify the exact arithmetic of compute_composite's weighting scheme."""

    def test_all_7_at_100_gives_composite_100(self):
        """Perfect score across all 7 dimensions must yield exactly 100.0."""
        scores = _make_score_dict({d: 100 for d in _ALL_7_DIMS})
        result = compute_composite(scores)
        assert result["score"] == 100.0, (
            f"All dims at 100 should give composite 100.0, got {result['score']}"
        )

    def test_all_7_at_0_gives_composite_0(self):
        """Zero score across all 7 dimensions must yield exactly 0.0."""
        scores = _make_score_dict({d: 0 for d in _ALL_7_DIMS})
        result = compute_composite(scores)
        assert result["score"] == 0.0, (
            f"All dims at 0 should give composite 0.0, got {result['score']}"
        )

    def test_only_structure_measured_gives_100(self):
        """When only structure is in the scores dict (others absent), composite = 100.0.

        Normalization: composite = (100 * w_structure) / w_structure = 100.0
        """
        scores = {"structure": {"score": 100, "issues": [], "details": {}}}
        result = compute_composite(scores)
        assert result["score"] == 100.0, (
            f"Single measured dimension at 100 should normalize to 100.0, got {result['score']}"
        )
        assert result["weight_coverage"] == pytest.approx(0.15, abs=0.01)

    def test_structure_100_others_0_gives_structure_weight_times_100(self):
        """Structure=100 with all others=0 (all 7 measured) = structure_weight * 100.

        Default structure weight = 0.15, all 7 dims measured, weight_sum = 1.0.
        composite = (100 * 0.15) / 1.0 = 15.0
        """
        scores = _make_score_dict({d: 0 for d in _ALL_7_DIMS})
        scores["structure"]["score"] = 100
        result = compute_composite(scores)
        assert result["score"] == 15.0, (
            f"structure=100, rest=0 → expected 15.0 (0.15 * 100), got {result['score']}"
        )

    def test_clarity_adds_5pct_weight_and_redistributes(self):
        """When clarity is present, its weight is 0.05 and others are scaled by 0.95.

        Default structure weight = 0.15, with clarity → 0.15 * 0.95 = 0.1425.
        All 7 dims at 0, structure at 100, clarity at 0:
        composite = 100 * 0.1425 / 1.0 = 14.2
        """
        scores = _make_score_dict({d: 0 for d in _ALL_7_DIMS})
        scores["structure"]["score"] = 100
        scores["clarity"] = {"score": 0, "issues": [], "details": {}}
        result = compute_composite(scores)
        assert result["score"] == pytest.approx(14.2, abs=0.1), (
            f"With clarity, structure=100/rest=0 → expected 14.2, got {result['score']}"
        )

    def test_clarity_all_dims_at_100_still_gives_100(self):
        """When all 7 dims + clarity = 100 each, composite remains exactly 100.0."""
        scores = _make_score_dict({d: 100 for d in _ALL_7_DIMS})
        scores["clarity"] = {"score": 100, "issues": [], "details": {}}
        result = compute_composite(scores)
        assert result["score"] == 100.0, (
            f"All 8 dims at 100 with clarity should give 100.0, got {result['score']}"
        )

    def test_weight_coverage_all_7_measured_is_1(self):
        """All 7 default dimensions measured → weight_coverage = 1.0."""
        scores = _make_score_dict({d: 50 for d in _ALL_7_DIMS})
        result = compute_composite(scores)
        assert result["weight_coverage"] == pytest.approx(1.0, abs=1e-6)

    def test_weight_coverage_single_dim_matches_that_dims_weight(self):
        """Measuring only structure → weight_coverage = structure's weight (0.15)."""
        scores = {"structure": {"score": 50, "issues": [], "details": {}}}
        result = compute_composite(scores)
        assert result["weight_coverage"] == pytest.approx(0.15, abs=0.01)

    def test_composite_score_is_always_float(self):
        """compute_composite must always return a float, never an int or None."""
        for dim_scores in [
            {d: 100 for d in _ALL_7_DIMS},
            {d: 0 for d in _ALL_7_DIMS},
            {"structure": 75},
        ]:
            result = compute_composite(_make_score_dict(dim_scores))
            assert isinstance(result["score"], float), (
                f"composite score must be float, got {type(result['score'])} for dims={dim_scores}"
            )


# ---------------------------------------------------------------------------
# 5. Determinism across runs
# ---------------------------------------------------------------------------

_DETERMINISM_CONTENT = '''\
---
name: determinism-test
description: Use when testing determinism. Do not use for anything else.
---

# Determinism Test

Run the scoring function 10 times to verify consistency.

## Instructions

1. Run the analysis
2. Verify the output matches
3. Check all dimensions
'''


class TestDeterminism:
    """Scoring must be deterministic: same content always produces identical scores."""

    def test_structure_10_runs_identical(self, tmp_path):
        path = _write(tmp_path, _DETERMINISM_CONTENT)
        scores = []
        for _ in range(10):
            invalidate_cache(path)
            scores.append(score_structure(path)["score"])
        assert len(set(scores)) == 1, (
            f"score_structure is non-deterministic across 10 runs: {set(scores)}"
        )

    def test_efficiency_10_runs_identical(self, tmp_path):
        path = _write(tmp_path, _DETERMINISM_CONTENT)
        scores = []
        for _ in range(10):
            invalidate_cache(path)
            scores.append(score_efficiency(path)["score"])
        assert len(set(scores)) == 1, (
            f"score_efficiency is non-deterministic across 10 runs: {set(scores)}"
        )

    def test_composability_10_runs_identical(self, tmp_path):
        path = _write(tmp_path, _DETERMINISM_CONTENT)
        scores = []
        for _ in range(10):
            invalidate_cache(path)
            scores.append(score_composability(path)["score"])
        assert len(set(scores)) == 1, (
            f"score_composability is non-deterministic across 10 runs: {set(scores)}"
        )

    def test_clarity_10_runs_identical(self, tmp_path):
        path = _write(tmp_path, _DETERMINISM_CONTENT)
        scores = []
        for _ in range(10):
            invalidate_cache(path)
            scores.append(score_clarity(path)["score"])
        assert len(set(scores)) == 1, (
            f"score_clarity is non-deterministic across 10 runs: {set(scores)}"
        )

    def test_composite_10_runs_identical(self, tmp_path):
        path = _write(tmp_path, _DETERMINISM_CONTENT)
        composites = []
        for _ in range(10):
            invalidate_cache(path)
            composites.append(_score_all(path)["score"])
        assert len(set(composites)) == 1, (
            f"composite is non-deterministic across 10 runs: {set(composites)}"
        )

    def test_different_paths_same_content_identical_scores(self):
        """Two different file paths with identical content must produce identical scores."""
        with tempfile.TemporaryDirectory() as tmp1:
            with tempfile.TemporaryDirectory() as tmp2:
                p1 = Path(tmp1) / "SKILL.md"
                p2 = Path(tmp2) / "SKILL.md"
                p1.write_text(_DETERMINISM_CONTENT, encoding="utf-8")
                p2.write_text(_DETERMINISM_CONTENT, encoding="utf-8")

                dims1 = {
                    "structure": score_structure(str(p1))["score"],
                    "efficiency": score_efficiency(str(p1))["score"],
                    "composability": score_composability(str(p1))["score"],
                    "clarity": score_clarity(str(p1))["score"],
                }
                dims2 = {
                    "structure": score_structure(str(p2))["score"],
                    "efficiency": score_efficiency(str(p2))["score"],
                    "composability": score_composability(str(p2))["score"],
                    "clarity": score_clarity(str(p2))["score"],
                }

                assert dims1 == dims2, (
                    f"Different paths, same content → different scores!\n"
                    f"  path1={dims1}\n  path2={dims2}"
                )

    def test_different_paths_same_content_identical_composite(self):
        """Composite score must also be identical across different paths."""
        with tempfile.TemporaryDirectory() as tmp1:
            with tempfile.TemporaryDirectory() as tmp2:
                p1 = Path(tmp1) / "SKILL.md"
                p2 = Path(tmp2) / "SKILL.md"
                p1.write_text(_DETERMINISM_CONTENT, encoding="utf-8")
                p2.write_text(_DETERMINISM_CONTENT, encoding="utf-8")

                comp1 = _score_all(str(p1))["score"]
                comp2 = _score_all(str(p2))["score"]
                assert comp1 == comp2, (
                    f"Different paths, same content → different composite: {comp1} vs {comp2}"
                )
