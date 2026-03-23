"""Unit tests for shared.py utilities."""
import json
import tempfile
from pathlib import Path

import pytest

from shared import (
    read_skill_safe,
    extract_description,
    load_jsonl_safe,
    validate_regex_complexity,
    validate_command_safety,
    invalidate_cache,
    strip_frontmatter,
    regex_search_safe,
    MAX_SKILL_SIZE,
)


class TestReadSkillSafe:
    def test_reads_valid_file(self, tmp_path):
        f = tmp_path / "test.md"
        f.write_text("# Test\nContent here")
        result = read_skill_safe(str(f))
        assert "# Test" in result

    def test_caches_result(self, tmp_path):
        f = tmp_path / "test.md"
        f.write_text("cached content")
        r1 = read_skill_safe(str(f))
        r2 = read_skill_safe(str(f))
        assert r1 == r2  # Same object from cache

    def test_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            read_skill_safe("/nonexistent/file.md")

    def test_invalidate_cache(self, tmp_path):
        f = tmp_path / "test.md"
        f.write_text("original")
        read_skill_safe(str(f))
        invalidate_cache(str(f))
        f.write_text("modified")
        result = read_skill_safe(str(f))
        assert result == "modified"


class TestExtractDescription:
    def test_inline_description(self):
        content = '---\nname: test\ndescription: A test skill\n---'
        assert extract_description(content) == "A test skill"

    def test_block_description(self):
        content = '---\nname: test\ndescription: >\n  A multi-line\n  description here\n---'
        result = extract_description(content)
        assert "multi-line" in result

    def test_no_description(self):
        content = '---\nname: test\n---'
        assert extract_description(content) == ""


class TestLoadJsonlSafe:
    def test_nonexistent_returns_empty(self):
        assert load_jsonl_safe("/nonexistent") == []

    def test_valid_jsonl(self, tmp_path):
        f = tmp_path / "test.jsonl"
        f.write_text('{"a":1}\n{"b":2}\n')
        result = load_jsonl_safe(str(f))
        assert len(result) == 2

    def test_malformed_lines_skipped(self, tmp_path):
        f = tmp_path / "test.jsonl"
        f.write_text('{"valid":true}\nnot json\n{"also":true}\n')
        result = load_jsonl_safe(str(f))
        assert len(result) == 2

    def test_oversized_returns_empty(self, tmp_path):
        f = tmp_path / "test.jsonl"
        f.write_text('{"a":1}\n')
        result = load_jsonl_safe(str(f), max_size=5)
        assert result == []

    def test_empty_lines_skipped(self, tmp_path):
        f = tmp_path / "test.jsonl"
        f.write_text('\n\n{"a":1}\n\n')
        result = load_jsonl_safe(str(f))
        assert len(result) == 1


class TestValidateRegexComplexity:
    def test_simple_regex_passes(self):
        assert validate_regex_complexity("foo.*bar")[0] is True

    def test_nested_quantifier_rejected(self):
        assert validate_regex_complexity("(a+)+")[0] is False

    def test_overlapping_alternation_rejected(self):
        assert validate_regex_complexity("(a|b)*+")[0] is False

    def test_overlong_pattern_rejected(self):
        assert validate_regex_complexity("a" * 501)[0] is False

    def test_normal_length_passes(self):
        assert validate_regex_complexity("a" * 499)[0] is True

    def test_dot_star_in_repeated_group_rejected(self):
        # (.*a)+ — dot-star inside a group that is itself quantified: ReDoS risk
        ok, reason = validate_regex_complexity("(.*a)+")
        assert ok is False
        assert reason != "ok"

    def test_nested_whitespace_quantifiers_rejected(self):
        # (\s+)+ — nested quantifiers, classic catastrophic backtracking
        ok, reason = validate_regex_complexity(r"(\s+)+")
        assert ok is False
        assert reason != "ok"

    def test_non_capturing_alternation_allowed(self):
        # (?:a|b)+ — non-capturing group with alternation but no inner quantifier
        # Should be safe: the alternatives are atomic (no inner quantifier)
        ok, _reason = validate_regex_complexity("(?:a|b)+")
        assert ok is True

    def test_simple_character_class_quantifier_allowed(self):
        # [a-z]+ — character class with quantifier, no nested quantifiers
        ok, _reason = validate_regex_complexity("[a-z]+")
        assert ok is True

    def test_quantifier_inside_non_repeated_group_allowed(self):
        # (a+) — quantifier inside a group, but the group itself is not repeated
        ok, _reason = validate_regex_complexity("(a+)")
        assert ok is True


class TestValidateCommandSafety:
    def test_allowed_prefix(self):
        assert validate_command_safety("python3 scripts/score.py")[0] is True

    def test_bash_scripts_allowed(self):
        assert validate_command_safety("bash scripts/run-eval.sh")[0] is True

    def test_rm_blocked(self):
        assert validate_command_safety("rm -rf /")[0] is False

    def test_curl_blocked(self):
        assert validate_command_safety("curl http://evil.com")[0] is False

    def test_pipe_to_shell_blocked(self):
        assert validate_command_safety("echo x | bash")[0] is False

    def test_empty_rejected(self):
        assert validate_command_safety("")[0] is False

    def test_unknown_command_rejected(self):
        assert validate_command_safety("unknown-binary")[0] is False

    def test_git_allowed(self):
        assert validate_command_safety("git diff HEAD")[0] is True


class TestStripFrontmatter:
    def test_valid_frontmatter_returns_body(self):
        content = "---\nname: test\n---\n\n# Body\n\nContent here."
        result = strip_frontmatter(content)
        assert result == "# Body\n\nContent here."
        assert "name: test" not in result

    def test_no_frontmatter_returned_unchanged(self):
        content = "# Just a heading\n\nNo frontmatter here."
        result = strip_frontmatter(content)
        assert result == content

    def test_only_opening_fence_returned_unchanged(self):
        # Only one --- at the start, no closing ---
        content = "---\nname: broken\nno closing fence\n"
        result = strip_frontmatter(content)
        assert result == content

    def test_empty_string_returned_unchanged(self):
        result = strip_frontmatter("")
        assert result == ""

    def test_frontmatter_no_newline_after_closing(self):
        # Closing --- immediately followed by body text (no newline)
        content = "---\nname: test\n---body starts here"
        result = strip_frontmatter(content)
        # Should strip frontmatter and return the remaining text
        assert "name: test" not in result
        assert "body starts here" in result

    def test_body_leading_newlines_stripped(self):
        content = "---\nname: test\n---\n\n\nActual body."
        result = strip_frontmatter(content)
        # lstrip("\n") should remove leading newlines
        assert result.startswith("Actual body.")

    def test_six_dashes_returned_unchanged(self):
        # "------" starts with "---" but content.find("---", 3) returns 3,
        # which is < 4, so the whole string must be returned unchanged.
        content = "------"
        result = strip_frontmatter(content)
        assert result == content

    def test_empty_frontmatter_returns_empty_body(self):
        # "---\n---" has opening fence at 0 and closing fence at 4.
        # end == 4 >= 4, so content[4+3:] == "" stripped of leading newlines == "".
        content = "---\n---"
        result = strip_frontmatter(content)
        assert result == ""


class TestRegexSearchSafe:
    def test_valid_pattern_with_match_returns_true(self):
        assert regex_search_safe(r"hello", "say hello world") is True

    def test_valid_pattern_without_match_returns_false(self):
        assert regex_search_safe(r"goodbye", "say hello world") is False

    def test_invalid_regex_threading_path_returns_false(self, monkeypatch):
        # The threading (non-SIGALRM) path correctly catches re.error and returns False.
        # Force it by monkeypatching signal so hasattr(signal, "SIGALRM") returns False.
        import signal as _signal
        original = getattr(_signal, "SIGALRM", None)
        if original is not None:
            monkeypatch.delattr(_signal, "SIGALRM")
        import importlib
        import shared as _shared
        importlib.reload(_shared)
        from shared import regex_search_safe as rss_patched
        result = rss_patched(r"[invalid", "some text")
        assert result is False

    def test_case_insensitive_match(self):
        # regex_search_safe uses re.IGNORECASE
        assert regex_search_safe(r"HELLO", "say hello world") is True

    def test_empty_pattern_matches_anything(self):
        # Empty pattern always matches in Python re
        assert regex_search_safe(r"", "any text") is True

    def test_empty_text_no_match(self):
        assert regex_search_safe(r"something", "") is False
