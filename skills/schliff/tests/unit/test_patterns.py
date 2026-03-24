"""Tests for recently modified regex patterns in scoring/patterns.py.

Covers:
- Five new composability patterns (v6.0.1)
- False positive guards for common skill prose
- Efficiency deduplication logic

Three pattern bugs are documented inline. Tests are written against
actual current behavior; known bugs are marked with BUG comments so
they fail visibly when the bug is fixed and need to be updated.
"""
import sys
from pathlib import Path

import pytest

# Ensure scripts/ is on path (also done by conftest.py, but explicit here
# so this file can be run standalone with `python -m pytest` from repo root)
SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from scoring.patterns import (
    _RE_ERROR_BEHAVIOR,
    _RE_IDEMPOTENCY,
    _RE_DEPENDENCY_DECL,
    _RE_NAMESPACE_ISOLATION,
    _RE_VERSION_COMPAT,
    _RE_ACTIONABLE_LINES,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def matches(pattern, text: str) -> bool:
    return bool(pattern.search(text))


# ---------------------------------------------------------------------------
# 1. _RE_ERROR_BEHAVIOR
# ---------------------------------------------------------------------------

class TestErrorBehavior:
    """Tests for _RE_ERROR_BEHAVIOR.

    Pattern (line 78-81 of patterns.py):
        (?i)(on\\s+error|error\\s+handling|if\\s+\\w+\\s+fails?|when\\s+\\w+\\s+fails?|
             graceful(?:ly)?\\s+(?:handle|degrade|fail)|recover(?:y|s)?\\s+(?:from|when))

    KNOWN BUG #1: 'if the command fails' does NOT match.
        Cause: if\\s+\\w+\\s+fails? allows only ONE \\w+ token between 'if' and 'fails'.
        'the command' is two words. Only 'if <single_word> fails' matches.
        Example that does work: 'if it fails', 'if script fails'.

    KNOWN BUG #2: 'graceful degradation' does NOT match.
        Cause: pattern is graceful(?:ly)?\\s+(?:handle|degrade|fail).
        'degradation' is not in the alternation. Only the verb forms match.
        Example that does work: 'gracefully degrade', 'graceful failure'.
    """

    # --- Should match ---

    def test_matches_on_error(self):
        assert matches(_RE_ERROR_BEHAVIOR, "on error, abort the run")

    def test_matches_error_handling(self):
        assert matches(_RE_ERROR_BEHAVIOR, "Error handling is described below")

    def test_matches_if_single_word_fails(self):
        # One word between 'if' and 'fails' — works as designed
        assert matches(_RE_ERROR_BEHAVIOR, "if it fails")
        assert matches(_RE_ERROR_BEHAVIOR, "if script fails")
        assert matches(_RE_ERROR_BEHAVIOR, "if validation fails, skip")

    def test_matches_when_single_word_fails(self):
        assert matches(_RE_ERROR_BEHAVIOR, "when parsing fails")
        assert matches(_RE_ERROR_BEHAVIOR, "when verification fail")

    def test_matches_gracefully_degrade(self):
        assert matches(_RE_ERROR_BEHAVIOR, "gracefully degrade to the fallback")

    def test_matches_graceful_handle(self):
        assert matches(_RE_ERROR_BEHAVIOR, "graceful handle of missing config")

    def test_matches_graceful_fail(self):
        assert matches(_RE_ERROR_BEHAVIOR, "graceful failure is preferred")

    def test_matches_recovery_from(self):
        assert matches(_RE_ERROR_BEHAVIOR, "recovery from network errors")

    def test_matches_recover_when(self):
        assert matches(_RE_ERROR_BEHAVIOR, "recover when the connection drops")

    # --- Should NOT match ---

    def test_no_match_bare_failure(self):
        assert not matches(_RE_ERROR_BEHAVIOR, "failure")

    def test_no_match_failure_in_prose(self):
        assert not matches(_RE_ERROR_BEHAVIOR, "there was a failure last week")

    def test_no_match_if_something_missing(self):
        # 'if something is missing from the description' — no 'fails'
        assert not matches(_RE_ERROR_BEHAVIOR, "if something is missing from the description")

    # --- KNOWN BUGS (document current behavior; update tests when fixed) ---

    def test_if_multi_word_fails_matched(self):
        """'if the command fails' matches with multi-word subjects."""
        assert matches(_RE_ERROR_BEHAVIOR, "if the command fails")
        assert matches(_RE_ERROR_BEHAVIOR, "if the build fails")

    def test_graceful_degradation_matched(self):
        """'graceful degradation' matches noun form."""
        assert matches(_RE_ERROR_BEHAVIOR, "graceful degradation")
        assert matches(_RE_ERROR_BEHAVIOR, "graceful degradation of the pipeline")


# ---------------------------------------------------------------------------
# 2. _RE_IDEMPOTENCY
# ---------------------------------------------------------------------------

class TestIdempotency:
    """Tests for _RE_IDEMPOTENCY.

    Pattern (line 82-85):
        (?i)(idempotent|safe to (?:re-?run|run (?:again|twice|multiple))|
             running (?:again|twice)|no side.?effects?|re-?entrant)
    """

    # --- Should match ---

    def test_matches_idempotent(self):
        assert matches(_RE_IDEMPOTENCY, "This operation is idempotent")

    def test_matches_safe_to_rerun(self):
        assert matches(_RE_IDEMPOTENCY, "safe to re-run multiple times")

    def test_matches_safe_to_run(self):
        assert matches(_RE_IDEMPOTENCY, "safe to run again after failure")

    def test_matches_safe_to_run_twice(self):
        assert matches(_RE_IDEMPOTENCY, "safe to run twice without side effects")

    def test_matches_no_side_effects(self):
        assert matches(_RE_IDEMPOTENCY, "no side effects on the filesystem")

    def test_matches_no_sideeffects_hyphen(self):
        assert matches(_RE_IDEMPOTENCY, "no side-effects guaranteed")

    def test_matches_running_again(self):
        assert matches(_RE_IDEMPOTENCY, "running again is safe")

    def test_matches_running_twice(self):
        assert matches(_RE_IDEMPOTENCY, "running twice produces the same result")

    def test_matches_reentrant(self):
        assert matches(_RE_IDEMPOTENCY, "The function is re-entrant")

    # --- Should NOT match ---

    def test_no_match_random_prose(self):
        assert not matches(_RE_IDEMPOTENCY, "random text here")

    def test_no_match_side_story(self):
        # 'side' in a different context must not match
        assert not matches(_RE_IDEMPOTENCY, "look at the side of the building")

    def test_no_match_run_once(self):
        assert not matches(_RE_IDEMPOTENCY, "run once to initialize")

    def test_no_match_safe_context_only(self):
        # 'safe' alone without the full phrase
        assert not matches(_RE_IDEMPOTENCY, "this is a safe operation")


# ---------------------------------------------------------------------------
# 3. _RE_DEPENDENCY_DECL
# ---------------------------------------------------------------------------

class TestDependencyDecl:
    """Tests for _RE_DEPENDENCY_DECL.

    Pattern (line 86-90):
        (?i)(requires?:\\s*\\w|depends? on|prerequisite|
             needs?\\s+(?:python|node|npm|pip|git|jq|bash|ruby|go)\\b|
             install\\s+\\w+\\s+first)

    KNOWN BUG #3: 'requires python 3.9' does NOT match.
        Cause: The 'requires?' branch needs a colon (requires?:\\s*\\w).
        The bare 'requires python' without colon is not covered.
        The 'needs?' branch covers 'needs python' but not 'requires python'.
        Fix: add a branch like requires?\\s+(?:python|node|npm|pip|git|...)\\b
    """

    # --- Should match ---

    def test_matches_depends_on_git(self):
        assert matches(_RE_DEPENDENCY_DECL, "depends on git for version control")

    def test_matches_prerequisite(self):
        assert matches(_RE_DEPENDENCY_DECL, "prerequisite: install docker first")

    def test_matches_requires_colon(self):
        # requires: <word> — the colon branch works
        assert matches(_RE_DEPENDENCY_DECL, "requires: python")
        assert matches(_RE_DEPENDENCY_DECL, "require: node")

    def test_matches_needs_python(self):
        assert matches(_RE_DEPENDENCY_DECL, "needs python to run")

    def test_matches_needs_git(self):
        assert matches(_RE_DEPENDENCY_DECL, "need git installed")

    def test_matches_needs_node(self):
        assert matches(_RE_DEPENDENCY_DECL, "needs node >= 18")

    def test_matches_install_first(self):
        assert matches(_RE_DEPENDENCY_DECL, "install docker first")
        assert matches(_RE_DEPENDENCY_DECL, "install jq first before running")

    def test_matches_depend_on(self):
        assert matches(_RE_DEPENDENCY_DECL, "depend on npm for package management")

    # --- Should NOT match ---

    def test_no_match_requires_attention(self):
        assert not matches(_RE_DEPENDENCY_DECL, "requires attention")

    def test_no_match_requires_effort(self):
        assert not matches(_RE_DEPENDENCY_DECL, "this requires significant effort")

    def test_no_match_needs_improvement(self):
        # 'needs' but not followed by a known tool name
        assert not matches(_RE_DEPENDENCY_DECL, "this needs improvement")

    # --- KNOWN BUG ---

    def test_requires_python_without_colon_matched(self):
        """'requires python 3.9' matches with space separator."""
        assert matches(_RE_DEPENDENCY_DECL, "requires python 3.9")
        assert matches(_RE_DEPENDENCY_DECL, "requires node >= 18")
        assert matches(_RE_DEPENDENCY_DECL, "requires git")


# ---------------------------------------------------------------------------
# 4. _RE_NAMESPACE_ISOLATION
# ---------------------------------------------------------------------------

class TestNamespaceIsolation:
    """Tests for _RE_NAMESPACE_ISOLATION.

    Pattern (line 91-94):
        (?i)(namespace\\s+\\w+|namespaced?\\b|__\\w+__|
             @[\\w-]+/[\\w-]+|plugin[_-]\\w+|scoped\\s+to\\b)
    """

    # --- Should match ---

    def test_matches_at_org_package(self):
        assert matches(_RE_NAMESPACE_ISOLATION, "@org/package")
        assert matches(_RE_NAMESPACE_ISOLATION, "@my-org/my-package")

    def test_matches_plugin_underscore(self):
        assert matches(_RE_NAMESPACE_ISOLATION, "plugin_name")
        assert matches(_RE_NAMESPACE_ISOLATION, "plugin_scoring_v2")

    def test_matches_plugin_hyphen(self):
        assert matches(_RE_NAMESPACE_ISOLATION, "plugin-format")

    def test_matches_dunder(self):
        assert matches(_RE_NAMESPACE_ISOLATION, "__dunder__")
        assert matches(_RE_NAMESPACE_ISOLATION, "__init__")
        assert matches(_RE_NAMESPACE_ISOLATION, "__all__")

    def test_matches_namespace_keyword(self):
        assert matches(_RE_NAMESPACE_ISOLATION, "namespace myapp")
        assert matches(_RE_NAMESPACE_ISOLATION, "namespace scoring_v2")

    def test_matches_namespaced(self):
        assert matches(_RE_NAMESPACE_ISOLATION, "namespaced output files")

    def test_matches_scoped_to(self):
        assert matches(_RE_NAMESPACE_ISOLATION, "scoped to the project directory")

    # --- Should NOT match ---

    def test_no_match_error_file_not_found(self):
        assert not matches(_RE_NAMESPACE_ISOLATION, "Error: file not found")

    def test_no_match_bare_scope(self):
        assert not matches(_RE_NAMESPACE_ISOLATION, "scope")
        assert not matches(_RE_NAMESPACE_ISOLATION, "the scope of this skill is")

    def test_no_match_at_mention_without_slash(self):
        # @username without package (no slash) — not an npm-style namespace
        assert not matches(_RE_NAMESPACE_ISOLATION, "@username mentioned this")

    def test_no_match_random_prose(self):
        assert not matches(_RE_NAMESPACE_ISOLATION, "use this for data processing")


# ---------------------------------------------------------------------------
# 5. _RE_VERSION_COMPAT
# ---------------------------------------------------------------------------

class TestVersionCompat:
    """Tests for _RE_VERSION_COMPAT.

    Pattern (line 95-99):
        (?i)(version\\s*[><=!]+\\s*[\\d.]+|compatible\\s+with\\s+\\w+\\s+v?\\d|
             requires?\\s+\\w+\\s*[><=]+\\s*[\\d.]+|minimum\\s+version|
             supported\\s+versions?|works\\s+with\\s+\\w+\\s+v?\\d+\\.\\d+)
    """

    # --- Should match ---

    def test_matches_compatible_with_python(self):
        assert matches(_RE_VERSION_COMPAT, "compatible with Python v3.9")
        assert matches(_RE_VERSION_COMPAT, "compatible with Python 3")

    def test_matches_requires_python_gte(self):
        assert matches(_RE_VERSION_COMPAT, "requires python >= 3.9")
        assert matches(_RE_VERSION_COMPAT, "requires node >= 18.0")

    def test_matches_requires_tool_lte(self):
        assert matches(_RE_VERSION_COMPAT, "requires bash <= 5.2")

    def test_matches_version_operator(self):
        assert matches(_RE_VERSION_COMPAT, "version >= 2.0")
        assert matches(_RE_VERSION_COMPAT, "version != 1.0")
        assert matches(_RE_VERSION_COMPAT, "version == 3.11")

    def test_matches_minimum_version(self):
        assert matches(_RE_VERSION_COMPAT, "minimum version required is 3.8")

    def test_matches_supported_versions(self):
        assert matches(_RE_VERSION_COMPAT, "supported versions: 3.8, 3.9, 3.10")
        assert matches(_RE_VERSION_COMPAT, "supported version: 2.x")

    def test_matches_works_with(self):
        assert matches(_RE_VERSION_COMPAT, "works with Python v3.9.1")
        assert matches(_RE_VERSION_COMPAT, "works with node v18.0")

    # --- Should NOT match ---

    def test_no_match_bare_version_prose(self):
        # "This is version 2.0 of the skill" — no operator, no 'compatible with' etc.
        assert not matches(_RE_VERSION_COMPAT, "This is version 2.0 of the skill")

    def test_no_match_version_number_only(self):
        assert not matches(_RE_VERSION_COMPAT, "v2.0 released today")
        assert not matches(_RE_VERSION_COMPAT, "v2.0")

    def test_no_match_version_in_filename(self):
        assert not matches(_RE_VERSION_COMPAT, "see CHANGELOG_v2.0.md for details")

    def test_no_match_changelog_context(self):
        assert not matches(_RE_VERSION_COMPAT, "Added in version 2.0")


# ---------------------------------------------------------------------------
# 6. False positive guards — common skill prose
# ---------------------------------------------------------------------------

class TestFalsePositives:
    """Common skill writing patterns that must NOT trigger composability patterns."""

    def test_encounter_error_not_error_behavior(self):
        """'encounter an error' describes when to trigger, not error handling."""
        text = "Use this skill when you encounter an error"
        assert not matches(_RE_ERROR_BEHAVIOR, text)

    def test_version_in_changelog_prose_not_compat(self):
        """'This is version 2.0 of the skill' is not a compatibility declaration."""
        text = "This is version 2.0 of the skill, released in January"
        assert not matches(_RE_VERSION_COMPAT, text)

    def test_scope_intro_not_namespace(self):
        """'The scope of this skill is...' is not a namespace isolation marker."""
        text = "The scope of this skill is limited to Python projects"
        assert not matches(_RE_NAMESPACE_ISOLATION, text)

    def test_error_word_alone_not_error_behavior(self):
        """'error' alone in a sentence is not error behavior documentation."""
        assert not matches(_RE_ERROR_BEHAVIOR, "The error message was unclear")
        assert not matches(_RE_ERROR_BEHAVIOR, "handle errors gracefully")  # 'errors' != 'error handling'

    def test_requires_soft_skills_not_dependency(self):
        """'requires attention / effort / review' must not match."""
        assert not matches(_RE_DEPENDENCY_DECL, "requires careful attention")
        assert not matches(_RE_DEPENDENCY_DECL, "requires a thorough review")

    def test_idempotency_false_positive_safe(self):
        """'safe' in general prose must not trigger idempotency."""
        assert not matches(_RE_IDEMPOTENCY, "it is safe to assume")
        assert not matches(_RE_IDEMPOTENCY, "safe practices include testing")


# ---------------------------------------------------------------------------
# 7. Efficiency deduplication logic
# ---------------------------------------------------------------------------

class TestEfficiencyDedup:
    """Tests for the deduplication logic in score_efficiency().

    Relevant code in efficiency.py (lines 47-48):
        raw_actionable = _RE_ACTIONABLE_LINES.findall(content)
        actionable_lines = len(set(m.strip().lower()[:60] for m in raw_actionable))

    IMPORTANT: _RE_ACTIONABLE_LINES.findall() returns only the matched VERB
    (no capturing group in the pattern), not the full line. This means the
    dedup is on the verb token, not on the full instruction text.

    Consequence: 'Run the build' and 'Run the tests' both produce 'run' and
    count as ONE unique instruction. This is arguably a bug in the dedup
    design (full-line dedup was the stated intent), but it is the current
    behavior and these tests document it accurately.
    """

    def _count_actionable(self, content: str) -> int:
        """Replicate the dedup logic from efficiency.py."""
        raw = _RE_ACTIONABLE_LINES.findall(content)
        return len(set(m.strip().lower()[:60] for m in raw))

    # --- Identical instructions ---

    def test_identical_instructions_count_as_one(self):
        content = "Run the build\nRun the build\nRun the build\n"
        assert self._count_actionable(content) == 1

    def test_identical_verb_different_objects_count_as_one(self):
        """'Run X' and 'Run Y' both yield verb 'run' — count as 1 (current behavior).

        NOTE: This documents a known limitation. The stated design intent was
        'near-duplicate instructions count as 1', but the implementation
        deduplicates at verb level, not sentence level.
        """
        content = "Run the build\nRun the tests\nRun the linter\n"
        # All three produce 'run' after findall -> deduped to 1
        assert self._count_actionable(content) == 1

    # --- Different verbs count separately ---

    def test_different_verbs_count_separately(self):
        content = "Run the build\nCheck the output\nCreate a new file\n"
        assert self._count_actionable(content) == 3

    def test_five_different_verbs(self):
        content = (
            "Run the tests\n"
            "Check the output\n"
            "Create a config file\n"
            "Install the dependencies\n"
            "Verify the result\n"
        )
        assert self._count_actionable(content) == 5

    # --- Non-actionable lines are ignored ---

    def test_non_actionable_lines_not_counted(self):
        content = "This is a description.\nSome prose here.\nNo action here.\n"
        assert self._count_actionable(content) == 0

    def test_mixed_actionable_and_prose(self):
        content = (
            "This skill helps you analyze code.\n"
            "Run the score script to get results.\n"
            "The output will show dimension scores.\n"
            "Check the issues list for details.\n"
        )
        # 'Run' and 'Check' are actionable; prose lines are not
        assert self._count_actionable(content) == 2

    # --- Near-duplicate full lines (same first 60 chars of verb) ---

    def test_near_duplicate_full_lines_via_verb_dedup(self):
        """Lines with very long identical verb prefixes deduplicate correctly.

        Since findall returns only the matched verb, dedup is verb-level.
        Two 'Run' lines always deduplicate regardless of the rest of the line.
        """
        content = (
            "Run " + "a" * 56 + " variant_A\n"
            "Run " + "a" * 56 + " variant_B\n"
        )
        # Both match 'Run', both deduplicate to 'run'
        assert self._count_actionable(content) == 1

    # --- Numbered instructions ---

    def test_numbered_instructions_count_correctly(self):
        """Numbered list format: '1. Run ...' is counted, but dedup includes the number prefix.

        The pattern matches '1. Run', '2. Check', '3. Run' as full tokens.
        After .lower()[:60], these become '1. run', '2. check', '3. run' — all distinct.
        So three numbered lines with two repeated verbs produce count=3, not count=2.

        This is a side effect of the pattern including the optional numeric prefix
        in the match: the number differentiates otherwise identical verbs.
        """
        content = "1. Run the setup script\n2. Check the output\n3. Run again if needed\n"
        # '1. Run', '2. Check', '3. Run' -> lowered: '1. run', '2. check', '3. run' -> count=3
        assert self._count_actionable(content) == 3

    # --- Case insensitivity ---

    def test_uppercase_lowercase_verbs_deduplicate(self):
        content = "Run the build\nRUN the build\nrun the build\n"
        # All match 'Run'/'RUN'/'run', lowercase[:60] -> all 'run'
        assert self._count_actionable(content) == 1
