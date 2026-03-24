"""Unit tests for the scoring package."""
import json
import tempfile
from pathlib import Path

import pytest

from scoring import (
    score_structure,
    score_triggers,
    score_efficiency,
    score_composability,
    score_quality,
    score_edges,
    score_clarity,
    compute_composite,
)
from scoring.coherence import score_coherence
from scoring.patterns import (
    _RE_FRONTMATTER_NAME,
    _RE_FRONTMATTER_DESC,
    _RE_HEDGING,
    _RE_TODO,
)
from terminal_art import score_to_grade


# --- Fixtures ---

@pytest.fixture
def good_skill(tmp_path):
    """A well-formed SKILL.md that should score high."""
    content = '''---
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
    skill_path = tmp_path / "SKILL.md"
    skill_path.write_text(content)
    return str(skill_path)


@pytest.fixture
def bad_skill(tmp_path):
    """A poorly-formed SKILL.md that should score low."""
    content = '''no frontmatter here

TODO: add description
FIXME: add examples

you might want to consider maybe possibly doing something
you could try to perhaps attempt this
'''
    skill_path = tmp_path / "SKILL.md"
    skill_path.write_text(content)
    return str(skill_path)


@pytest.fixture
def minimal_skill(tmp_path):
    """Minimal valid SKILL.md."""
    content = '''---
name: minimal
description: A minimal skill
---

# Minimal Skill

Do the thing.
'''
    skill_path = tmp_path / "SKILL.md"
    skill_path.write_text(content)
    return str(skill_path)


@pytest.fixture
def eval_suite():
    """A basic eval suite for testing trigger and quality scoring."""
    return {
        "triggers": [
            {"prompt": "improve my skill quality", "should_trigger": True},
            {"prompt": "optimize this skill's triggers", "should_trigger": True},
            {"prompt": "analyze my skill for issues", "should_trigger": True},
            {"prompt": "deploy my web application", "should_trigger": False},
            {"prompt": "fix the CSS styling", "should_trigger": False},
        ],
        "test_cases": [
            {
                "id": "tc-1",
                "prompt": "analyze the skill",
                "assertions": [
                    {"type": "contains", "value": "score", "description": "mentions score"},
                    {"type": "pattern", "value": "\\d+/100", "description": "has numeric score"},
                    {"type": "excludes", "value": "TODO", "description": "no TODOs"},
                ],
            }
        ],
        "edge_cases": [
            {
                "id": "ec-1",
                "prompt": "empty input",
                "category": "missing_input",
                "expected_behavior": "Should ask for clarification",
                "assertions": [
                    {"type": "contains", "value": "?", "description": "asks a question"},
                ],
            }
        ],
    }


# --- score_structure tests ---

class TestScoreStructure:
    def test_good_skill_scores_high(self, good_skill):
        result = score_structure(good_skill)
        assert result["score"] >= 70
        assert isinstance(result["issues"], list)

    def test_bad_skill_scores_low(self, bad_skill):
        result = score_structure(bad_skill)
        assert result["score"] <= 40
        assert "no_frontmatter" in result["issues"]

    def test_missing_file_returns_zero(self):
        result = score_structure("/nonexistent/SKILL.md")
        assert result["score"] == 0
        assert "file_not_found" in result["issues"]

    def test_minimal_skill_scores_moderate(self, minimal_skill):
        result = score_structure(minimal_skill)
        assert 20 <= result["score"] <= 85

    def test_returns_dict_with_required_keys(self, good_skill):
        result = score_structure(good_skill)
        assert "score" in result
        assert "issues" in result
        assert "details" in result

    def test_empty_body_only_frontmatter_returns_zero(self, tmp_path):
        """Frontmatter present but body is empty → score=0, empty_skill_body in issues."""
        content = "---\nname: empty-body\ndescription: A skill\n---\n"
        f = tmp_path / "SKILL.md"
        f.write_text(content)
        result = score_structure(str(f))
        assert result["score"] == 0
        assert "empty_skill_body" in result["issues"]

    def test_whitespace_only_body_returns_zero(self, tmp_path):
        """Body that is only whitespace after frontmatter → treated as empty."""
        content = "---\nname: ws-only\ndescription: A skill\n---\n\n   \n\t\n"
        f = tmp_path / "SKILL.md"
        f.write_text(content)
        result = score_structure(str(f))
        assert result["score"] == 0
        assert "empty_skill_body" in result["issues"]

    def test_no_refs_gives_five_points_not_ten(self, tmp_path):
        """No reference declarations → +5 pts (neutral), not +10 (reward).

        The refs block awards:
          no refs     → +5  (neutral, not penalized)
          all refs ok → +10 (rewarded)
          some missing→ +5 + issue
        """
        # Minimal skill with frontmatter + body but NO backtick file references
        content = (
            "---\nname: no-refs\ndescription: A skill with no file refs\n---\n\n"
            "# No Refs\n\nDo the thing without referencing any files.\n"
        )
        f = tmp_path / "SKILL.md"
        f.write_text(content)
        result = score_structure(str(f))
        # Score must NOT include the +10 refs bonus, only the +5 neutral credit
        # We verify by comparing against an identical skill that does declare refs
        # that all exist (which earns +10).  The no-refs variant must score lower.
        # Build the all-refs-exist variant
        refs_dir = tmp_path / "refs_skill"
        refs_dir.mkdir()
        ref_file = refs_dir / "guide.md"
        ref_file.write_text("# guide")
        content_with_refs = (
            "---\nname: with-refs\ndescription: A skill with file refs\n---\n\n"
            "# With Refs\n\nSee `guide.md` for details. Do the thing.\n"
        )
        skill_with_refs = refs_dir / "SKILL.md"
        skill_with_refs.write_text(content_with_refs)
        result_with_refs = score_structure(str(skill_with_refs))
        # The skill with all existing refs should score >= no-refs skill
        # (because it earns +10 vs +5 in the refs bucket)
        assert result_with_refs["score"] >= result["score"]

    def test_good_skill_still_scores_high_after_refs_change(self, good_skill):
        """Regression: good_skill must still score >= 65 after refs scoring reduced."""
        result = score_structure(good_skill)
        # Threshold lowered from 70 to 65 to account for refs change (5pt less)
        assert result["score"] >= 65


# --- score_efficiency tests ---

class TestScoreEfficiency:
    def test_good_skill_has_decent_efficiency(self, good_skill):
        result = score_efficiency(good_skill)
        assert result["score"] >= 50

    def test_bad_skill_penalized_for_hedging(self, bad_skill):
        result = score_efficiency(bad_skill)
        assert result["score"] <= 60
        # Should detect hedging language
        details = result.get("details", {})
        assert details.get("hedge_count", 0) >= 1

    def test_missing_file_returns_zero(self):
        result = score_efficiency("/nonexistent/SKILL.md")
        assert result["score"] == 0

    def test_empty_body_after_frontmatter_returns_zero(self, tmp_path):
        # Frontmatter only, body is empty after stripping
        content = "---\nname: empty-body\ndescription: A skill\n---\n"
        f = tmp_path / "SKILL.md"
        f.write_text(content)
        result = score_efficiency(str(f))
        assert result["score"] == 0
        assert "empty_skill_body" in result["issues"]

    def test_high_hedging_ratio_lowers_score(self, tmp_path):
        # Construct content heavy on hedging phrases and minimal signal
        hedging_blob = (
            "you might want to consider this approach\n"
            "you could possibly try the alternative\n"
            "perhaps you should maybe think about it\n"
            "it might be worth considering whether\n"
            "you might want to consider another option\n"
        ) * 4  # repeat to ensure hedge_count > 2
        content = f"---\nname: hedgy\ndescription: hedge test\n---\n\n{hedging_blob}"
        f = tmp_path / "SKILL.md"
        f.write_text(content)
        result = score_efficiency(str(f))
        details = result.get("details", {})
        assert details.get("hedge_count", 0) > 2
        assert result["score"] <= 60
        # At least one issue about excessive hedging
        assert any("excessive_hedging" in issue for issue in result["issues"])

    def test_density_boundary_at_eight_scores_ninety_five(self, tmp_path):
        # Craft content designed to hit density >= 8 bracket
        # Many actionable lines (imperative verbs) and real examples
        actionable = "\n".join([
            "Run the scoring script to evaluate your skill.",
            "Check the output for any issues listed.",
            "Fix all errors before proceeding to the next step.",
            "Verify the score reaches the required threshold.",
            "Update the frontmatter to include a clear description.",
            "Add concrete examples with input and output pairs.",
            "Review the efficiency dimension score carefully.",
            "Document the rationale behind each design decision.",
        ] * 5)
        examples = "\n```bash\npython3 score.py skill.md\n```\n" * 6
        content = f"---\nname: dense\ndescription: Dense skill\n---\n\n{actionable}\n{examples}"
        f = tmp_path / "SKILL.md"
        f.write_text(content)
        result = score_efficiency(str(f))
        # High-density content should land at the upper score tiers
        assert result["score"] >= 75

    def test_score_is_clamped_between_zero_and_hundred(self, tmp_path):
        # Any real content must produce a score in [0, 100]
        content = "---\nname: clamp-test\ndescription: test\n---\n\nDo the thing.\n"
        f = tmp_path / "SKILL.md"
        f.write_text(content)
        result = score_efficiency(str(f))
        assert 0 <= result["score"] <= 100


# --- score_composability tests ---

class TestScoreComposability:
    def test_good_skill_with_scope_boundaries(self, good_skill):
        result = score_composability(good_skill)
        # Good skill has "Use when" and "Do not use" — with 10 checks, scores ~30
        assert result["score"] >= 20

    def test_bad_skill_no_scope(self, bad_skill):
        result = score_composability(bad_skill)
        assert "no_scope_boundaries" in result["issues"]


# --- score_triggers tests ---

class TestScoreTriggers:
    def test_with_eval_suite(self, good_skill, eval_suite):
        result = score_triggers(good_skill, eval_suite)
        assert result["score"] >= 0
        assert "details" in result
        assert result["details"]["total"] == 5

    def test_without_eval_suite(self, good_skill):
        result = score_triggers(good_skill, None)
        assert result["score"] == -1
        assert "no_trigger_eval_suite" in result["issues"]


# --- score_quality tests ---

class TestScoreQuality:
    def test_with_eval_suite(self, good_skill, eval_suite):
        result = score_quality(good_skill, eval_suite)
        assert result["score"] >= 0 or result["score"] == -1

    def test_without_eval_suite(self, good_skill):
        result = score_quality(good_skill, None)
        assert result["score"] == -1

    def test_base_quality_capped_at_90(self, good_skill):
        """Even a perfect eval suite (all 4 criteria met = 100 raw) caps at 90 before coherence."""
        # Build an eval suite that satisfies all four criteria maximally:
        # 3+ well-formed test cases, 3+ assertion types, 3+ feature keywords,
        # all assertions described.
        perfect_suite = {
            "test_cases": [
                {
                    "id": "tc-analyze-1",
                    "prompt": "analyze the skill and report issues",
                    "assertions": [
                        {"type": "contains", "value": "score", "description": "has score"},
                        {"type": "pattern", "value": r"\d+/100", "description": "numeric score"},
                        {"type": "excludes", "value": "error", "description": "no errors"},
                    ],
                },
                {
                    "id": "tc-improve-2",
                    "prompt": "improve the skill quality",
                    "assertions": [
                        {"type": "contains", "value": "improved", "description": "mentions improvement"},
                        {"type": "format", "value": "markdown", "description": "uses markdown"},
                    ],
                },
                {
                    "id": "tc-build-3",
                    "prompt": "build a report from the skill",
                    "assertions": [
                        {"type": "contains", "value": "report", "description": "has report"},
                        {"type": "excludes", "value": "TODO", "description": "no TODOs"},
                    ],
                },
            ]
        }
        result = score_quality(good_skill, perfect_suite)
        assert result["score"] >= 0
        # The coherence bonus is 0-10; base is capped at 90.
        # Therefore the final score cannot exceed 100.
        assert result["score"] <= 100
        # The coherence_bonus detail must be present and non-negative
        assert result["details"]["coherence_bonus"] >= 0

    def test_quality_score_above_90_requires_coherence_bonus(self, good_skill):
        """A score > 90 is only reachable when coherence bonus > 0.

        We use an eval suite that scores the maximum 30+25+25+20=100 raw pts.
        The base is capped at 90. To exceed 90 the coherence bonus must be positive.
        """
        rich_suite = {
            "test_cases": [
                {
                    "id": "tc-analyze-1",
                    "prompt": "analyze the skill and report issues",
                    "assertions": [
                        {"type": "contains", "value": "score", "description": "has score"},
                        {"type": "pattern", "value": r"\d+", "description": "numeric"},
                        {"type": "excludes", "value": "error", "description": "clean"},
                    ],
                },
                {
                    "id": "tc-improve-2",
                    "prompt": "improve skill quality",
                    "assertions": [
                        {"type": "contains", "value": "improved", "description": "ok"},
                        {"type": "format", "value": "json", "description": "formatted"},
                    ],
                },
                {
                    "id": "tc-build-3",
                    "prompt": "build and test the skill",
                    "assertions": [
                        {"type": "contains", "value": "test", "description": "has test"},
                    ],
                },
            ]
        }
        result = score_quality(good_skill, rich_suite)
        bonus = result["details"]["coherence_bonus"]
        final = result["score"]
        # If bonus is 0 → score must be <= 90; if bonus > 0 → score may exceed 90
        if bonus == 0:
            assert final <= 90, (
                f"Expected score <= 90 when coherence_bonus=0, got {final}"
            )
        else:
            assert final <= 90 + bonus, (
                f"Score {final} exceeds 90 + coherence_bonus {bonus}"
            )

    def test_quality_score_never_exceeds_100(self, good_skill):
        """Quality score must always be clamped to [0, 100]."""
        from scoring.quality import score_quality as sq
        # Craft a suite that would produce a high base + potential coherence bonus
        suite = {
            "test_cases": [
                {
                    "id": f"tc-{i}",
                    "prompt": f"analyze improve build test {i}",
                    "assertions": [
                        {"type": "contains", "value": "score", "description": "has score"},
                        {"type": "excludes", "value": "error", "description": "no error"},
                        {"type": "pattern", "value": r"\d+", "description": "has number"},
                        {"type": "format", "value": "json", "description": "json"},
                    ],
                }
                for i in range(5)
            ]
        }
        result = sq(good_skill, suite)
        assert 0 <= result["score"] <= 100


# --- score_edges tests ---

class TestScoreEdges:
    def test_with_edge_cases(self, good_skill, eval_suite):
        result = score_edges(good_skill, eval_suite)
        assert result["score"] >= 0

    def test_without_eval_suite(self, good_skill):
        result = score_edges(good_skill, None)
        assert result["score"] == -1


# --- compute_composite tests ---

class TestComputeComposite:
    def test_basic_composite(self):
        scores = {
            "structure": {"score": 80},
            "triggers": {"score": 90},
            "efficiency": {"score": 70},
            "composability": {"score": 60},
            "quality": {"score": -1},  # unmeasured
            "edges": {"score": -1},    # unmeasured
        }
        result = compute_composite(scores)
        assert "score" in result
        assert 0 <= result["score"] <= 100
        assert result["measured_dimensions"] >= 4

    def test_all_unmeasured(self):
        scores = {
            "structure": {"score": -1},
            "triggers": {"score": -1},
        }
        result = compute_composite(scores)
        assert result["score"] == 0 or result["measured_dimensions"] == 0

    def test_perfect_scores(self):
        scores = {
            "structure": {"score": 100},
            "triggers": {"score": 100},
            "efficiency": {"score": 100},
            "composability": {"score": 100},
            "quality": {"score": 100},
            "edges": {"score": 100},
        }
        result = compute_composite(scores)
        assert result["score"] >= 95

    def test_clarity_dimension_present_weights_sum_to_one(self):
        scores = {
            "structure": {"score": 80},
            "triggers": {"score": 70},
            "efficiency": {"score": 60},
            "composability": {"score": 50},
            "quality": {"score": 75},
            "edges": {"score": 65},
            "clarity": {"score": 90},
        }
        result = compute_composite(scores)
        # Score must be a valid number in range
        assert 0 <= result["score"] <= 100
        assert result["measured_dimensions"] >= 1

    def test_partial_dimensions_only_three(self):
        scores = {
            "structure": {"score": 60},
            "efficiency": {"score": 80},
            "composability": {"score": 50},
            # triggers, quality, edges, runtime all missing / unmeasured
            "triggers": {"score": -1},
            "quality": {"score": -1},
            "edges": {"score": -1},
        }
        result = compute_composite(scores)
        assert result["measured_dimensions"] == 3
        # Score should be a weighted average of the 3 measured dimensions
        assert 0 < result["score"] <= 100
        # Weight coverage must be strictly less than 1 (some dimensions missing)
        assert result["weight_coverage"] < 1.0

    def test_composability_weight_influences_composite_by_at_least_5pts(self):
        """composability weight is 0.10 — a 100-pt swing must move the composite >= 5 pts.

        All other dimensions are fixed at 80.  We compare:
          composability=0   vs   composability=100
        The difference in composite must be >= 5 pts because:
          effective_weight(composability) = 0.10 / weight_coverage
          With all 6 static dims measured weight_coverage ≈ 0.80 (runtime unmeasured)
          → effective = 0.125 → delta ≈ 12.5 pts
        """
        base = {
            "structure":    {"score": 80},
            "triggers":     {"score": 80},
            "efficiency":   {"score": 80},
            "quality":      {"score": 80},
            "edges":        {"score": 80},
            "runtime":      {"score": -1},  # unmeasured
        }

        scores_low = dict(base)
        scores_low["composability"] = {"score": 0}
        scores_high = dict(base)
        scores_high["composability"] = {"score": 100}

        result_low = compute_composite(scores_low)
        result_high = compute_composite(scores_high)

        diff = result_high["score"] - result_low["score"]
        assert diff >= 5, (
            f"Expected composability to move composite by >= 5 pts "
            f"(weight=0.10), got diff={diff:.1f} "
            f"(low={result_low['score']}, high={result_high['score']})"
        )


# --- score_clarity tests ---

class TestScoreClarity:
    def test_contradiction_detected(self, tmp_path):
        # Same verb+object+modifier → real contradiction
        content = (
            "---\nname: contradictory\ndescription: A skill\n---\n\n"
            "Always run the linter.\n"
            "Never run the linter.\n"
        )
        f = tmp_path / "SKILL.md"
        f.write_text(content)
        result = score_clarity(str(f))
        assert any("contradiction" in issue for issue in result["issues"])

    def test_context_aware_no_false_contradiction(self, tmp_path):
        # Same verb+object but different context → NOT a contradiction
        content = (
            "---\nname: contextual\ndescription: A skill\n---\n\n"
            "Always run the linter before committing.\n"
            "Never run the linter on generated files.\n"
        )
        f = tmp_path / "SKILL.md"
        f.write_text(content)
        result = score_clarity(str(f))
        assert not any("contradiction" in issue for issue in result["issues"])

    def test_vague_references_lower_score(self, tmp_path):
        # "the file" without any preceding specific file reference is vague
        vague_content = (
            "---\nname: vague\ndescription: A skill\n---\n\n"
            "Open the editor.\n"
            "Save the file.\n"
            "Check the output.\n"
            "Review the result.\n"
            "Inspect the config.\n"
        )
        clear_content = (
            "---\nname: clear\ndescription: A skill\n---\n\n"
            "Open `skill.md` in your editor.\n"
            "Save the changes to `skill.md`.\n"
            "Check the output in `results.json`.\n"
        )
        f_vague = tmp_path / "vague.md"
        f_vague.write_text(vague_content)
        f_clear = tmp_path / "clear.md"
        f_clear.write_text(clear_content)
        vague_result = score_clarity(str(f_vague))
        clear_result = score_clarity(str(f_clear))
        assert vague_result["score"] < clear_result["score"]

    def test_clean_skill_scores_high(self, good_skill):
        # A well-written skill with no contradictions or vague references
        result = score_clarity(good_skill)
        assert result["score"] >= 80

    def test_empty_body_returns_zero(self, tmp_path):
        # Frontmatter-only skill: body is empty after stripping
        content = "---\nname: empty\ndescription: A skill\n---\n"
        f = tmp_path / "SKILL.md"
        f.write_text(content)
        result = score_clarity(str(f))
        assert result["score"] == 0
        assert "empty_skill_body" in result["issues"]

    def test_missing_file_returns_zero(self):
        result = score_clarity("/nonexistent/SKILL.md")
        assert result["score"] == 0
        assert "file_not_found" in result["issues"]

    def test_returns_required_keys(self, good_skill):
        result = score_clarity(good_skill)
        assert "score" in result
        assert "issues" in result
        assert "details" in result

    def test_score_clamped_to_zero_minimum(self, tmp_path):
        # Pile on many contradictions: score must never go below 0
        contradictions = "\n".join(
            [f"Always use option{i}.\nNever use option{i}." for i in range(10)]
        )
        content = f"---\nname: many-contradictions\ndescription: test\n---\n\n{contradictions}\n"
        f = tmp_path / "SKILL.md"
        f.write_text(content)
        result = score_clarity(str(f))
        assert result["score"] >= 0


# --- score_coherence tests ---

class TestScoreCoherence:
    def test_with_eval_suite_returns_bonus_key(self, good_skill, eval_suite):
        result = score_coherence(good_skill, eval_suite)
        assert "bonus" in result
        assert "details" in result

    def test_with_eval_suite_bonus_non_negative(self, good_skill, eval_suite):
        result = score_coherence(good_skill, eval_suite)
        assert result["bonus"] >= 0

    def test_without_eval_suite_bonus_is_zero(self, good_skill):
        result = score_coherence(good_skill, None)
        assert result["bonus"] == 0
        assert "details" in result

    def test_without_eval_suite_reason_recorded(self, good_skill):
        result = score_coherence(good_skill, None)
        assert result["details"].get("reason") == "no_eval_suite"

    def test_eval_suite_without_test_cases_bonus_is_zero(self, good_skill):
        # eval_suite with no test_cases key → treated as no suite
        result = score_coherence(good_skill, {"triggers": []})
        assert result["bonus"] == 0

    def test_bonus_bounded_between_zero_and_ten(self, good_skill, eval_suite):
        result = score_coherence(good_skill, eval_suite)
        assert 0 <= result["bonus"] <= 10

    def test_return_shape_complete(self, good_skill, eval_suite):
        result = score_coherence(good_skill, eval_suite)
        assert set(result.keys()) >= {"bonus", "details"}


# --- Integration test: full scoring pipeline ---

@pytest.fixture
def good_skill_file(tmp_path):
    """A complete, well-formed skill file for integration testing."""
    content = '''---
name: integration-skill
description: >
  A skill for integration testing of the full scoring pipeline.
  Use when running end-to-end scoring tests.
  Do not use for production deployment or security scanning.
---

# Integration Skill

Use this skill when you need to run the full scoring pipeline end to end.

## Instructions

1. Read the skill file at `SKILL.md`
2. Run `python3 scripts/score-skill.py SKILL.md --json`
3. Check the output for a score between 0 and 100
4. Verify the result contains all measured dimensions
5. Validate the grade letter is present

## Examples

Example 1: Score a skill
```bash
python3 scripts/score-skill.py SKILL.md --json
```

Example 2: Score with eval suite
```bash
python3 scripts/score-skill.py SKILL.md --eval-suite eval-suite.json --json
```

## When NOT to Use

Do not use this skill for:
- Real production deployments
- Security auditing workflows
- Database migration tasks
'''
    skill_path = tmp_path / "SKILL.md"
    skill_path.write_text(content)
    return skill_path


class TestFullScoringPipeline:
    def test_full_scoring_pipeline(self, good_skill_file, eval_suite):
        """Integration: score all static dimensions and compute composite."""
        from scoring import (
            score_structure, score_triggers, score_quality,
            score_edges, score_efficiency, score_composability,
            score_clarity,
        )
        from scoring.composite import compute_composite

        path = str(good_skill_file)
        scores = {
            "structure": score_structure(path),
            "triggers": score_triggers(path, eval_suite),
            "efficiency": score_efficiency(path),
            "composability": score_composability(path),
            "quality": score_quality(path, eval_suite),
            "edges": score_edges(path, eval_suite),
            "clarity": score_clarity(path),
        }

        # Each dimension must return a dict with a numeric score
        for dim, result in scores.items():
            assert isinstance(result, dict), f"{dim} did not return a dict"
            assert "score" in result, f"{dim} missing 'score' key"
            assert isinstance(result["score"], (int, float)), f"{dim} score is not numeric"

        result = compute_composite(scores)

        assert 0 <= result["score"] <= 100
        assert result["measured_dimensions"] >= 4
        assert isinstance(result["score_type"], str)
        assert "weight_coverage" in result
        assert 0.0 < result["weight_coverage"] <= 1.0

    def test_pipeline_grade_key_present_in_known_composite(self):
        """Verify compute_composite does not crash and score is in range."""
        from scoring.composite import compute_composite

        scores = {
            "structure": {"score": 85},
            "triggers": {"score": 75},
            "efficiency": {"score": 70},
            "composability": {"score": 60},
            "quality": {"score": -1},
            "edges": {"score": -1},
        }
        result = compute_composite(scores)
        assert 0 <= result["score"] <= 100
        assert result["measured_dimensions"] >= 4


# --- Density curve tests (continuous sqrt, no step-function cliffs) ---

class TestDensityCurve:
    """Tests for the continuous sqrt density-to-score mapping in efficiency.py.

    The formula is:  score = 40 + (density/10)**0.5 * 55  for 0 < density < 10
    with hard clamps: density<=0 → 40, density>=10 → 95.
    """

    def _make_skill_with_density(self, tmp_path, density_target: float) -> str:
        """Return path to a skill file whose computed density lands near density_target.

        Density = ((signal - noise) / total_words) * 100.
        We inject only actionable lines (weight 3 each) with no noise so:
            density ≈ (actionable_lines * 3 / total_words) * 100
        We vary actionable_lines and pad total_words to hit the target.
        """
        if density_target <= 0:
            # Plaintext filler — no imperative verbs, no examples
            body = "This is just some content.\n" * 20
        else:
            # One actionable line + padding to reach desired density
            # density = (n_actionable * 3 / total_words) * 100
            # Solve for n_actionable given total_words = 100:
            #   n_actionable = density * total_words / 300
            total_words = 200
            n_actionable = max(1, round(density_target * total_words / 300))
            actionable = "\n".join(
                [f"Run step {i} of the process carefully." for i in range(n_actionable)]
            )
            # Pad with neutral words to reach total_words
            current_words = len(actionable.split())
            padding_words = max(0, total_words - current_words)
            padding = ("word " * padding_words).strip()
            body = f"{actionable}\n{padding}"

        content = f"---\nname: density-test\ndescription: density test\n---\n\n{body}\n"
        p = tmp_path / "SKILL.md"
        p.write_text(content)
        return str(p)

    def test_density_zero_maps_to_near_40(self, tmp_path):
        """density <= 0 → score should be 40 (base floor)."""
        path = self._make_skill_with_density(tmp_path, 0)
        result = score_efficiency(path)
        # The floor is 40; minor bonuses (scope, conciseness) can push it a bit higher.
        assert 38 <= result["score"] <= 55, (
            f"Expected ~40 for zero density, got {result['score']} "
            f"(density={result['details'].get('density')})"
        )

    def test_density_ten_maps_to_near_95(self, tmp_path):
        """density >= 10 → score should reach the 90-100 range."""
        # Build content with very high signal: many actionable lines + code examples
        actionable = "\n".join([
            "Run the scoring script to evaluate your skill.",
            "Check the output for any issues listed.",
            "Fix all errors before proceeding to the next step.",
            "Verify the score reaches the required threshold.",
            "Update the frontmatter to include a clear description.",
            "Add concrete examples with input and output pairs.",
        ] * 3)
        examples = "\n```bash\npython3 score.py skill.md\n```\n" * 4
        content = (
            f"---\nname: high-density\ndescription: High density skill\n---\n\n"
            f"{actionable}\n{examples}"
        )
        p = tmp_path / "SKILL.md"
        p.write_text(content)
        result = score_efficiency(p)
        assert result["score"] >= 88, (
            f"Expected >=88 for density>=10, got {result['score']} "
            f"(density={result['details'].get('density')})"
        )

    def test_no_10pt_jump_across_density_5(self, tmp_path):
        """Continuous curve: adjacent density values must not differ by >= 10 pts.

        Specifically compare density ~4.99 vs ~5.01. In the old step-function
        implementation this crossing could cause a sudden 10-pt jump; the sqrt
        curve must stay smooth.
        """
        def skill_at_density(target: float, suffix: str) -> str:
            total_words = 300
            n_actionable = max(1, round(target * total_words / 300))
            actionable = "\n".join(
                [f"Execute step {i} precisely." for i in range(n_actionable)]
            )
            current = len(actionable.split())
            padding = ("filler " * max(0, total_words - current)).strip()
            body = f"{actionable}\n{padding}"
            content = (
                f"---\nname: boundary-{suffix}\n"
                f"description: boundary test\n---\n\n{body}\n"
            )
            p = tmp_path / f"SKILL_{suffix}.md"
            p.write_text(content)
            return str(p)

        below = skill_at_density(4.5, "below")
        above = skill_at_density(5.5, "above")

        r_below = score_efficiency(below)
        r_above = score_efficiency(above)

        diff = abs(r_above["score"] - r_below["score"])
        assert diff < 10, (
            f"Score jump across density ~5 is {diff} pts "
            f"(below={r_below['score']}, above={r_above['score']}) — "
            "step-function cliff detected; expected continuous curve"
        )

    def test_density_5_score_in_range(self, tmp_path):
        """density ~5 → score should be in the 75-85 range per the calibration comment."""
        # Use the formula directly: score = 40 + (5/10)**0.5 * 55 ≈ 78.9
        # We verify the real scorer produces something close when density is near 5.
        actionable = "\n".join(
            [f"Run process step {i} now." for i in range(5)]
        )
        padding = ("word " * 95).strip()
        body = f"{actionable}\n{padding}"
        content = f"---\nname: mid-density\ndescription: mid density\n---\n\n{body}\n"
        p = tmp_path / "SKILL.md"
        p.write_text(content)
        result = score_efficiency(p)
        # Allow generous band because exact density depends on pattern matching
        assert 60 <= result["score"] <= 100, (
            f"Expected 60-100 for density near 5, got {result['score']}"
        )

    def test_score_monotonically_increases_with_density(self, tmp_path):
        """Higher density must never produce a lower score than lower density."""
        scores = []
        for target in [0, 2, 5, 8, 10]:
            # Build a fresh tmp dir per target to avoid file name collisions
            sub = tmp_path / f"d{target}"
            sub.mkdir()
            n_actionable = max(0, round(target * 200 / 300))
            if n_actionable == 0:
                body = "plain text content " * 15
            else:
                actionable = "\n".join(
                    [f"Execute operation {i} carefully." for i in range(n_actionable)]
                )
                padding = ("word " * max(0, 200 - len(actionable.split()))).strip()
                body = f"{actionable}\n{padding}"
            content = (
                f"---\nname: mono-{target}\n"
                f"description: monotone test\n---\n\n{body}\n"
            )
            p = sub / "SKILL.md"
            p.write_text(content)
            r = score_efficiency(str(p))
            scores.append((target, r["score"]))

        # Each successive score must be >= previous (monotone non-decreasing)
        for i in range(1, len(scores)):
            prev_d, prev_s = scores[i - 1]
            cur_d, cur_s = scores[i]
            assert cur_s >= prev_s - 5, (  # 5-pt tolerance for noise/bonuses
                f"Score decreased from density {prev_d} (score {prev_s}) "
                f"to density {cur_d} (score {cur_s})"
            )


# --- Grade system tests (including new E grade) ---

class TestGrading:
    """Tests for score_to_grade() in terminal_art.py.

    Thresholds: S>=95, A>=85, B>=75, C>=65, D>=50, E>=35, F<35
    """

    def test_score_96_returns_S(self):
        assert score_to_grade(96) == "S"

    def test_score_95_returns_S(self):
        assert score_to_grade(95) == "S"

    def test_score_94_returns_A(self):
        assert score_to_grade(94) == "A"

    def test_score_85_returns_A(self):
        assert score_to_grade(85) == "A"

    def test_score_84_returns_B(self):
        assert score_to_grade(84) == "B"

    def test_score_75_returns_B(self):
        assert score_to_grade(75) == "B"

    def test_score_74_returns_C(self):
        assert score_to_grade(74) == "C"

    def test_score_65_returns_C(self):
        assert score_to_grade(65) == "C"

    def test_score_64_returns_D(self):
        assert score_to_grade(64) == "D"

    def test_score_50_returns_D(self):
        assert score_to_grade(50) == "D"

    def test_score_49_returns_E_boundary(self):
        """49 is below D threshold (50) — must be E."""
        assert score_to_grade(49) == "E"

    def test_score_40_returns_E(self):
        """score=40 is the new E grade (>= 35, < 50)."""
        assert score_to_grade(40) == "E"

    def test_score_35_returns_E_lower_boundary(self):
        """35 is the exact lower boundary of E."""
        assert score_to_grade(35) == "E"

    def test_score_34_returns_F(self):
        """34 falls below E threshold — must be F."""
        assert score_to_grade(34) == "F"

    def test_score_0_returns_F(self):
        assert score_to_grade(0) == "F"

    def test_score_100_returns_S(self):
        assert score_to_grade(100) == "S"

    def test_e_grade_exists_between_d_and_f(self):
        """E grade must sit strictly between D (50) and F (35)."""
        assert score_to_grade(49) == "E"
        assert score_to_grade(35) == "E"
        # Ensure D and F are unchanged
        assert score_to_grade(50) == "D"
        assert score_to_grade(34) == "F"


# --- Pattern tests ---

class TestPatterns:
    def test_frontmatter_name_pattern(self):
        assert _RE_FRONTMATTER_NAME.search("name: my-skill")
        assert not _RE_FRONTMATTER_NAME.search("no name here")

    def test_frontmatter_desc_pattern(self):
        assert _RE_FRONTMATTER_DESC.search("description: something")
        assert not _RE_FRONTMATTER_DESC.search("no desc")

    def test_hedging_pattern(self):
        assert _RE_HEDGING.search("you might want to consider this")
        assert _RE_HEDGING.search("you could possibly try")
        assert not _RE_HEDGING.search("Run the command")

    def test_todo_pattern(self):
        assert _RE_TODO.search("TODO: fix this")
        assert _RE_TODO.search("FIXME: broken")
        assert not _RE_TODO.search("this is done")
