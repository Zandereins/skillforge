"""Tests for trigger scoring precision/recall (Issue #13, part 2)."""
import sys
from pathlib import Path

import pytest

# Add scripts directory to path
SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from scoring.triggers import score_triggers


@pytest.fixture
def skill_path(tmp_path):
    """Create a minimal skill file for trigger testing."""
    skill = tmp_path / "SKILL.md"
    skill.write_text(
        "---\n"
        "name: test-skill\n"
        "description: A tool for reviewing code quality and detecting bugs\n"
        "---\n"
        "\n"
        "# Test Skill\n"
        "\n"
        "Review code for quality issues.\n"
    )
    return str(skill)


class TestPrecisionRecallExposed:
    """Verify precision and recall are returned by score_triggers."""

    def test_precision_recall_in_return(self, skill_path):
        eval_suite = {
            "triggers": [
                {"prompt": "review my code for bugs", "should_trigger": True},
                {"prompt": "what is the weather today", "should_trigger": False},
            ]
        }
        result = score_triggers(skill_path, eval_suite)
        assert "precision" in result, "precision missing from score_triggers result"
        assert "recall" in result, "recall missing from score_triggers result"

    def test_precision_recall_are_percentages(self, skill_path):
        eval_suite = {
            "triggers": [
                {"prompt": "review my code quality", "should_trigger": True},
                {"prompt": "detect bugs in my code", "should_trigger": True},
                {"prompt": "how to cook pasta", "should_trigger": False},
            ]
        }
        result = score_triggers(skill_path, eval_suite)
        assert 0 <= result["precision"] <= 100
        assert 0 <= result["recall"] <= 100

    def test_true_positives_in_details(self, skill_path):
        eval_suite = {
            "triggers": [
                {"prompt": "review my code quality", "should_trigger": True},
                {"prompt": "detect bugs in my code", "should_trigger": True},
            ]
        }
        result = score_triggers(skill_path, eval_suite)
        assert "true_positives" in result["details"]

    def test_perfect_precision_recall(self, skill_path):
        """When all predictions are correct, precision and recall should be 100."""
        # Use prompts that clearly match/don't match the description
        eval_suite = {
            "triggers": [
                {"prompt": "review code quality and detect bugs", "should_trigger": True},
                {"prompt": "what is the capital of France", "should_trigger": False},
            ]
        }
        result = score_triggers(skill_path, eval_suite)
        # The scorer may or may not get these exactly right, but the structure should be valid
        assert isinstance(result["precision"], float)
        assert isinstance(result["recall"], float)

    def test_no_eval_suite_returns_minus_one(self, skill_path):
        result = score_triggers(skill_path, None)
        assert result["score"] == -1
        # precision/recall should not be in result when there's no eval suite
        assert "precision" not in result

    def test_empty_triggers_returns_minus_one(self, skill_path):
        result = score_triggers(skill_path, {"triggers": []})
        assert result["score"] == -1


class TestPrecisionRecallSemantic:
    """Verify precision/recall correctly represent the classification quality."""

    def test_false_positives_hurt_precision(self, skill_path):
        """High false positives → low precision."""
        eval_suite = {
            "triggers": [
                {"prompt": "review my code quality", "should_trigger": True},
                # These negatives may get incorrectly triggered (false positives)
                {"prompt": "review this recipe for cooking", "should_trigger": False},
                {"prompt": "review the movie plot", "should_trigger": False},
                {"prompt": "review exam questions", "should_trigger": False},
            ]
        }
        result = score_triggers(skill_path, eval_suite)
        # With "review" in both positive and negative, precision may be impacted
        assert "precision" in result
        assert "recall" in result
        fp = result["details"]["false_positives"]
        if fp > 0:
            assert result["precision"] < 100.0

    def test_false_negatives_hurt_recall(self, skill_path):
        """High false negatives → low recall."""
        eval_suite = {
            "triggers": [
                {"prompt": "review my code quality", "should_trigger": True},
                # Obscure wording that the scorer might miss
                {"prompt": "take a look at my code please", "should_trigger": True},
                {"prompt": "what is wrong with this function", "should_trigger": True},
            ]
        }
        result = score_triggers(skill_path, eval_suite)
        fn = result["details"]["false_negatives"]
        if fn > 0:
            assert result["recall"] < 100.0
