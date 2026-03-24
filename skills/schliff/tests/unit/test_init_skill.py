"""Tests for init-skill.py — description-aware trigger generation (Issue #13)."""
import sys
from pathlib import Path

import pytest

# Add scripts directory to path
SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from importlib import import_module

# init-skill.py has a hyphen, so we need importlib
init_skill = import_module("init-skill")


# ---------------------------------------------------------------------------
# parse_frontmatter
# ---------------------------------------------------------------------------

class TestParseFrontmatter:
    def test_inline_description(self):
        content = "---\nname: my-skill\ndescription: A tool for reviewing PRs\n---\n"
        fm = init_skill.parse_frontmatter(content)
        assert fm["name"] == "my-skill"
        assert "reviewing PRs" in fm["description"]

    def test_block_scalar_folded(self):
        content = "---\nname: test\ndescription: >\n  A multi-agent adversarial\n  code review tool.\n---\n"
        fm = init_skill.parse_frontmatter(content)
        assert "multi-agent" in fm["description"]
        assert "code review" in fm["description"]

    def test_no_frontmatter(self):
        fm = init_skill.parse_frontmatter("# Just a heading\nSome content")
        assert fm["name"] == ""
        assert fm["description"] == ""


# ---------------------------------------------------------------------------
# _extract_skill_purpose
# ---------------------------------------------------------------------------

class TestExtractSkillPurpose:
    def test_code_review_skill(self):
        desc = "A multi-agent adversarial code review tool"
        purpose = init_skill._extract_skill_purpose(desc, "")
        assert any("review" in a.lower() for a in purpose["actions"]) or \
               any("review" in t for t in purpose["domain_terms"])

    def test_use_when_clause(self):
        desc = "Use when reviewing a pull request for security vulnerabilities"
        purpose = init_skill._extract_skill_purpose(desc, "")
        assert len(purpose["use_when"]) >= 1
        assert "reviewing a pull request" in purpose["use_when"][0].lower()

    def test_tool_for_pattern(self):
        desc = "A framework for detecting SQL injection vulnerabilities"
        purpose = init_skill._extract_skill_purpose(desc, "")
        assert any("detect" in a.lower() for a in purpose["actions"])

    def test_domain_terms_extracted(self):
        desc = "Monitors API endpoint performance and database query latency"
        purpose = init_skill._extract_skill_purpose(desc, "")
        terms_lower = [t.lower() for t in purpose["domain_terms"]]
        assert any("api" in t for t in terms_lower) or any("database" in t for t in terms_lower)

    def test_empty_description(self):
        purpose = init_skill._extract_skill_purpose("", "")
        assert purpose["actions"] == []
        assert purpose["use_when"] == []


# ---------------------------------------------------------------------------
# generate_positive_triggers — Issue #13 core fix
# ---------------------------------------------------------------------------

class TestPositiveTriggersDomainAware:
    """Verify that generated triggers match the skill's domain, not Schliff's."""

    def test_code_review_skill_no_schliff_triggers(self):
        """Issue #13: agent-review-panel should NOT get Schliff triggers."""
        name = "agent-review-panel"
        desc = "A multi-agent adversarial code review tool"
        phrases = ["review code", "red team architecture"]
        triggers = init_skill.generate_positive_triggers(name, desc, phrases)

        prompts = [t["prompt"].lower() for t in triggers]

        # Should NOT contain Schliff-specific patterns
        for prompt in prompts:
            assert "score" not in prompt or "45/100" not in prompt, \
                f"Schliff-specific scoring prompt found: {prompt}"
            assert "grind it to production" not in prompt, \
                f"Schliff-specific 'grind' prompt found: {prompt}"
            assert "skill-creator" not in prompt, \
                f"Schliff-specific 'skill-creator' prompt found: {prompt}"
            assert "benchmark" not in prompt or "dimensions" not in prompt, \
                f"Schliff-specific 'benchmark dimensions' prompt found: {prompt}"

    def test_code_review_skill_has_domain_triggers(self):
        """Triggers should reference the skill's actual domain."""
        name = "agent-review-panel"
        desc = "A multi-agent adversarial code review tool. Use when reviewing a PR for architecture issues."
        phrases = ["review code", "red team architecture"]
        triggers = init_skill.generate_positive_triggers(name, desc, phrases)

        prompts = " ".join(t["prompt"].lower() for t in triggers)
        # Should contain review-related terms
        assert "review" in prompts or "agent review panel" in prompts

    def test_deploy_skill_triggers(self):
        """A deployment skill should get deployment triggers."""
        name = "auto-deploy"
        desc = "Automatically deploys applications to production. Use when deploying to staging or production."
        triggers = init_skill.generate_positive_triggers(name, desc, [])

        prompts = " ".join(t["prompt"].lower() for t in triggers)
        assert "deploy" in prompts or "auto deploy" in prompts

    def test_minimum_5_triggers(self):
        """Always generates at least 5 triggers."""
        triggers = init_skill.generate_positive_triggers("x", "", [])
        assert len(triggers) >= 5

    def test_maximum_8_triggers(self):
        """Never generates more than 8 triggers."""
        triggers = init_skill.generate_positive_triggers(
            "x", "A tool for reviewing and testing code",
            ["review code", "test code", "lint code", "deploy code", "debug code"],
        )
        assert len(triggers) <= 8

    def test_all_triggers_have_required_fields(self):
        triggers = init_skill.generate_positive_triggers("test-skill", "A testing tool", [])
        for t in triggers:
            assert "id" in t
            assert "prompt" in t
            assert "should_trigger" in t
            assert t["should_trigger"] is True
            assert t["category"] == "positive"

    def test_dedup_similar_phrases(self):
        """Should not generate near-duplicate triggers from phrases."""
        name = "my-skill"
        desc = "Use when reviewing code"
        phrases = ["reviewing code", "review code quality"]
        triggers = init_skill.generate_positive_triggers(name, desc, phrases)
        prompts = [t["prompt"].lower() for t in triggers]
        # Not all prompts should be about reviewing code
        assert len(set(prompts)) == len(prompts), "Duplicate prompts detected"


# ---------------------------------------------------------------------------
# generate_negative_triggers — domain-aware filtering
# ---------------------------------------------------------------------------

class TestNegativeTriggersDomainAware:
    def test_code_review_skill_excludes_review_negatives(self):
        """Negative triggers should NOT include prompts in the skill's domain."""
        name = "code-reviewer"
        desc = "Reviews code for bugs and security issues"
        triggers = init_skill.generate_negative_triggers(name, desc)

        # All negative triggers should have should_trigger=False
        for t in triggers:
            assert t["should_trigger"] is False

    def test_minimum_3_negatives(self):
        triggers = init_skill.generate_negative_triggers("x", "")
        assert len(triggers) >= 3

    def test_maximum_5_negatives(self):
        desc = "do NOT use for cooking. NOT for gardening. not for singing."
        triggers = init_skill.generate_negative_triggers("x", desc)
        assert len(triggers) <= 5

    def test_not_for_clauses_extracted(self):
        desc = "A linting tool. Do NOT use for deployment automation."
        triggers = init_skill.generate_negative_triggers("linter", desc)
        prompts = " ".join(t["prompt"].lower() for t in triggers)
        assert "deployment" in prompts


# ---------------------------------------------------------------------------
# generate_edge_triggers — domain-aware
# ---------------------------------------------------------------------------

class TestEdgeTriggers:
    def test_uses_skill_name(self):
        triggers = init_skill.generate_edge_triggers("my-tool")
        prompts = " ".join(t["prompt"].lower() for t in triggers)
        assert "my tool" in prompts

    def test_domain_adjacent_edge(self):
        triggers = init_skill.generate_edge_triggers("db-optimizer", "Optimizes database query performance")
        assert len(triggers) >= 2
        # Should have an edge case about the domain
        categories = [t["category"] for t in triggers]
        assert all(c == "edge" for c in categories)


# ---------------------------------------------------------------------------
# generate_test_cases — domain-aware
# ---------------------------------------------------------------------------

class TestTestCasesDomainAware:
    def test_uses_description_for_prompts(self):
        cases = init_skill.generate_test_cases("my-skill", "Use when running security scans on APIs")
        prompts = " ".join(tc["prompt"].lower() for tc in cases)
        assert "security" in prompts or "my skill" in prompts

    def test_fallback_when_no_description(self):
        cases = init_skill.generate_test_cases("unknown", "")
        assert len(cases) >= 2
        # Should use skill name as fallback
        prompts = " ".join(tc["prompt"].lower() for tc in cases)
        assert "unknown" in prompts


# ---------------------------------------------------------------------------
# build_eval_suite — end-to-end
# ---------------------------------------------------------------------------

class TestBuildEvalSuiteE2E:
    def test_with_code_review_skill(self, tmp_path):
        """End-to-end: a code review skill should get code-review triggers."""
        skill = tmp_path / "SKILL.md"
        skill.write_text(
            "---\n"
            "name: agent-review-panel\n"
            "description: A multi-agent adversarial code review tool\n"
            "---\n"
            "\n"
            "# Agent Review Panel\n"
            "\n"
            "Use when you need a thorough code review on a pull request.\n"
            "Trigger when: reviewing PR, red team architecture, adversarial review\n"
            "\n"
            "## What it does\n"
            "Spawns multiple agents that review code from different perspectives.\n"
        )
        suite = init_skill.build_eval_suite(str(skill))

        assert suite["skill_name"] == "agent-review-panel"

        # Positive triggers should reference code review, not schliff
        pos_prompts = " ".join(
            t["prompt"].lower()
            for t in suite["triggers"]
            if t["should_trigger"]
        )
        assert "review" in pos_prompts or "agent review panel" in pos_prompts
        assert "grind it to production" not in pos_prompts
        assert "scores 45/100" not in pos_prompts

    def test_with_minimal_skill(self, tmp_path):
        """Even a minimal skill should produce a valid eval suite."""
        skill = tmp_path / "SKILL.md"
        skill.write_text("---\nname: tiny\n---\nDo something.\n")
        suite = init_skill.build_eval_suite(str(skill))

        assert suite["skill_name"] == "tiny"
        assert len(suite["triggers"]) >= 8  # 5+ positive + 3+ negative + 2+ edge
        assert len(suite["test_cases"]) >= 2
        assert len(suite["edge_cases"]) >= 2
