"""Tests for token budget estimation in formats.py."""
from __future__ import annotations

import sys
from pathlib import Path

# Add scripts directory to path so we can import scoring.formats
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))

from scoring.formats import (
    FORMAT_TOKEN_BUDGETS,
    check_token_budget,
    estimate_tokens,
)


class TestEstimateTokens:
    """Tests for the estimate_tokens function."""

    def test_known_string(self) -> None:
        # 20 chars -> 5 tokens
        assert estimate_tokens("a" * 20) == 5

    def test_empty_string(self) -> None:
        assert estimate_tokens("") == 0

    def test_short_string(self) -> None:
        # 3 chars -> 0 tokens (integer division)
        assert estimate_tokens("abc") == 0

    def test_exact_multiple(self) -> None:
        assert estimate_tokens("a" * 100) == 25


class TestFormatTokenBudgets:
    """Tests for the FORMAT_TOKEN_BUDGETS constant."""

    def test_has_all_expected_keys(self) -> None:
        expected = {"skill.md", "claude.md", "cursorrules", "agents.md", "unknown"}
        assert set(FORMAT_TOKEN_BUDGETS.keys()) == expected

    def test_values_are_positive_ints(self) -> None:
        for fmt, budget in FORMAT_TOKEN_BUDGETS.items():
            assert isinstance(budget, int), f"{fmt} budget is not int"
            assert budget > 0, f"{fmt} budget is not positive"


class TestCheckTokenBudget:
    """Tests for the check_token_budget function."""

    def test_within_budget_small_content(self) -> None:
        # skill.md budget is 1000 tokens = ~4000 chars
        content = "x" * 100  # 25 tokens, well within 1000
        result = check_token_budget(content, "skill.md")
        assert result["within_budget"] is True
        assert result["tokens"] == 25
        assert result["budget"] == 1000
        assert result["severity"] == "ok"

    def test_over_budget(self) -> None:
        # cursorrules budget is 500 tokens = ~2000 chars
        content = "x" * 8000  # 2000 tokens, way over 500
        result = check_token_budget(content, "cursorrules")
        assert result["within_budget"] is False
        assert result["tokens"] == 2000
        assert result["budget"] == 500
        assert result["severity"] == "over"

    def test_severity_ok(self) -> None:
        # 10% of budget -> ok
        content = "x" * 400  # 100 tokens out of 1000
        result = check_token_budget(content, "skill.md")
        assert result["severity"] == "ok"
        assert result["ratio"] < 0.8

    def test_severity_warning(self) -> None:
        # 90% of budget -> warning
        # skill.md budget = 1000 tokens, 900 tokens = 3600 chars
        content = "x" * 3600
        result = check_token_budget(content, "skill.md")
        assert result["severity"] == "warning"
        assert 0.8 <= result["ratio"] <= 1.0

    def test_severity_over(self) -> None:
        # 150% of budget -> over
        # skill.md budget = 1000, 1500 tokens = 6000 chars
        content = "x" * 6000
        result = check_token_budget(content, "skill.md")
        assert result["severity"] == "over"
        assert result["ratio"] > 1.0

    def test_unknown_format_uses_default_budget(self) -> None:
        content = "x" * 100
        result = check_token_budget(content, "nonexistent_format")
        assert result["budget"] == FORMAT_TOKEN_BUDGETS["unknown"]

    def test_ratio_calculation(self) -> None:
        # 4000 chars = 1000 tokens, skill.md budget = 1000 -> ratio 1.0
        content = "x" * 4000
        result = check_token_budget(content, "skill.md")
        assert result["ratio"] == 1.0
        assert result["within_budget"] is True

    def test_return_keys(self) -> None:
        result = check_token_budget("hello", "skill.md")
        assert set(result.keys()) == {"tokens", "budget", "within_budget", "ratio", "severity"}
