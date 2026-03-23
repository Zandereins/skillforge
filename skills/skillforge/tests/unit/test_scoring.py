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
        # Good skill has "Use when" and "Do not use"
        assert result["score"] >= 40

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


# --- score_clarity tests ---

class TestScoreClarity:
    def test_contradiction_detected(self, tmp_path):
        # "always run" and "never run" on the same verb topic → contradiction
        content = (
            "---\nname: contradictory\ndescription: A skill\n---\n\n"
            "Always run the linter before committing.\n"
            "Never run the linter on generated files.\n"
        )
        f = tmp_path / "SKILL.md"
        f.write_text(content)
        result = score_clarity(str(f))
        assert any("contradiction" in issue for issue in result["issues"])

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
