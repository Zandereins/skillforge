#!/usr/bin/env python3
"""Schliff — Shared Utilities

Centralized constants, file I/O, and common helpers.
Single source of truth — imported by all scoring and analysis modules.
"""
from __future__ import annotations

import json
import re
import sys
import threading
from pathlib import Path
from typing import Optional

# Maximum skill file size (1 MB) to prevent DoS via large inputs
MAX_SKILL_SIZE = 1_000_000

# Maximum entries in the file cache to prevent unbounded memory growth
MAX_CACHE_ENTRIES = 500

# Module-level file cache to avoid redundant reads within a single invocation
_file_cache: dict[str, str] = {}

# Known scoring dimensions for validation
VALID_DIMENSIONS = {
    "structure", "triggers", "quality", "edges",
    "efficiency", "composability", "clarity", "runtime",
}

# --- Regex for description extraction ---
_RE_DESC_BLOCK = re.compile(
    r"^description:\s*[>|]-?\s*\n((?:[ \t]+.+\n)*)", re.MULTILINE
)
_RE_DESC_INLINE = re.compile(r'^description:\s*"?(.+?)"?\s*$', re.MULTILINE)


def strip_frontmatter(content: str) -> str:
    """Strip YAML frontmatter (---...---) from skill content."""
    if content.startswith("---"):
        end = content.find("---", 3)
        if end >= 4:
            return content[end + 3:].lstrip("\n")
    return content


def invalidate_cache(skill_path: str) -> None:
    """Invalidate the file cache for a given skill path."""
    key = str(Path(skill_path).resolve())
    _file_cache.pop(key, None)


def read_skill_safe(skill_path: str) -> str:
    """Read a skill file with size limit enforcement and caching.

    Reads first, then checks size (avoids TOCTOU race condition).
    Rejects symlinks to prevent reading arbitrary files via crafted paths.
    """
    raw = Path(skill_path)
    if raw.is_symlink():
        raise ValueError(f"Skill path is a symlink (rejected): {skill_path}")
    p = raw.resolve()
    key = str(p)
    if key in _file_cache:
        return _file_cache[key]
    if not p.exists():
        raise FileNotFoundError(f"Skill file not found: {skill_path}")
    content = p.read_text(encoding="utf-8", errors="replace")
    if len(content) > MAX_SKILL_SIZE:
        raise ValueError(f"Skill file exceeds {MAX_SKILL_SIZE} bytes")
    if len(_file_cache) >= MAX_CACHE_ENTRIES:
        _file_cache.pop(next(iter(_file_cache)))
    _file_cache[key] = content
    return content


def extract_description(content: str) -> str:
    """Extract the description field from YAML frontmatter.

    Handles inline, block scalar (> and |) formats.
    """
    match = _RE_DESC_BLOCK.search(content)
    if match:
        return match.group(1).strip()
    match = _RE_DESC_INLINE.search(content)
    if match:
        return match.group(1).strip()
    return ""


def estimate_token_cost(skill_path: str) -> int:
    """Estimate token cost when this skill is loaded into context.

    Counts words in SKILL.md + all files in references/ directory.
    Uses 1.3 tokens/word approximation (standard for English text with code).
    Returns estimated token count.
    """
    total_words = 0

    # Read SKILL.md content
    try:
        content = read_skill_safe(skill_path)
        total_words += len(content.split())
    except (FileNotFoundError, ValueError):
        return 0

    # Check for references/ directory alongside SKILL.md
    refs_dir = Path(skill_path).parent / "references"
    if refs_dir.is_dir() and not refs_dir.is_symlink():
        for ref_file in sorted(refs_dir.glob("*.md")):
            if ref_file.is_symlink():
                continue
            try:
                ref_content = ref_file.read_text(encoding="utf-8", errors="replace")
                if len(ref_content) <= MAX_SKILL_SIZE:
                    total_words += len(ref_content.split())
            except (OSError, PermissionError):
                continue

    return round(total_words * 1.3)


def load_eval_suite(skill_path: str) -> Optional[dict]:
    """Auto-discover and load eval-suite.json from skill directory."""
    skill_dir = Path(skill_path).parent
    auto_path = skill_dir / "eval-suite.json"
    if auto_path.exists():
        try:
            raw = auto_path.read_text(encoding="utf-8")
            if len(raw) > MAX_SKILL_SIZE:
                print(f"Warning: eval-suite.json exceeds {MAX_SKILL_SIZE} bytes, skipping", file=sys.stderr)
                return None
            return json.loads(raw)
        except json.JSONDecodeError as e:
            print(f"Warning: malformed eval-suite.json: {e}", file=sys.stderr)
    return None


def build_scores(skill_path: str, eval_suite: Optional[dict] = None,
                  include_runtime: bool = False, fmt: Optional[str] = None) -> dict:
    """Build the standard scoring dict for a skill.

    Centralizes the dimension-scoring calls used by score, badge, and doctor.
    Supports non-SKILL.md formats (CLAUDE.md, .cursorrules, AGENTS.md) by
    normalizing content to SKILL.md shape before scoring — zero scorer changes.

    Args:
        fmt: Optional format override. When provided, skips auto-detection.
             Useful when the filename doesn't match the actual format
             (e.g., a file named 'instructions.md' that is CLAUDE.md-style).
    """
    import os
    import tempfile
    from scoring.formats import detect_format, normalize_content

    if fmt is None:
        fmt = detect_format(skill_path)
    tmp_path: Optional[str] = None
    if fmt != "skill.md":
        content = read_skill_safe(skill_path)
        normalized = normalize_content(content, fmt)
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8"
        )
        tmp.write(normalized)
        tmp.close()
        tmp_path = tmp.name
        skill_path = tmp_path  # scorers now see normalized content

    try:
        # Lazy imports to avoid circular deps and keep CLI startup fast
        from scoring import (
            score_structure, score_triggers, score_efficiency,
            score_composability, score_quality, score_edges,
            score_clarity,
        )

        scores = {
            "structure": score_structure(skill_path),
            "triggers": score_triggers(skill_path, eval_suite),
            "quality": score_quality(skill_path, eval_suite),
            "edges": score_edges(skill_path, eval_suite),
            "efficiency": score_efficiency(skill_path),
            "composability": score_composability(skill_path),
            "clarity": score_clarity(skill_path),
        }

        if include_runtime:
            from scoring import score_runtime
            scores["runtime"] = score_runtime(skill_path, eval_suite, enabled=False)
    finally:
        if tmp_path is not None:
            os.unlink(tmp_path)

    return scores


def validate_regex_complexity(pattern: str, max_length: int = 500) -> tuple[bool, str]:
    """Reject regex patterns with catastrophic backtracking potential.

    Returns (is_safe, reason).
    """
    if len(pattern) > max_length:
        return False, f"pattern too long ({len(pattern)} > {max_length})"

    # Detect nested quantifiers: (a+)+, (a*)+, (a+)*, etc.
    nested_quant = re.compile(r'[+*]\)?[+*?{]')
    if nested_quant.search(pattern):
        return False, "nested quantifiers detected (potential ReDoS)"

    # Detect overlapping alternations with quantifiers.
    # Non-capturing groups (?:...) are excluded: (?:a|b)+ is safe because
    # the alternatives are atomic and cannot cause catastrophic backtracking.
    overlap = re.compile(r'\((?!\?:)[^)]*\|[^)]*\)[+*]{1,2}')
    if overlap.search(pattern):
        return False, "overlapping alternation with quantifier (potential ReDoS)"

    # Dot-star or dot-plus inside a repeated group: (.*X)+
    group_inner_quant = re.compile(r'\([^)]*[.][*+][^)]*\)[+*?{]')
    if group_inner_quant.search(pattern):
        return False, "dot-wildcard quantifier inside repeated group (potential ReDoS)"

    return True, "ok"


def regex_search_safe(pattern: str, text: str, timeout: int = 2) -> bool:
    """Regex search with timeout to prevent ReDoS from user-supplied patterns.

    Runs the regex in a daemon thread with a timeout. Returns False on
    timeout, invalid pattern (re.error), or no match. This approach is
    thread-safe (unlike SIGALRM which is per-process) and portable across
    all platforms.
    """
    result: list[bool] = [False]
    error: list[Exception | None] = [None]

    def _search() -> None:
        try:
            result[0] = bool(re.search(pattern, text, re.IGNORECASE))
        except re.error as e:
            error[0] = e

    t = threading.Thread(target=_search, daemon=True)
    t.start()
    t.join(timeout=timeout)

    if t.is_alive():
        print(
            f"Warning: regex timed out after {timeout}s on pattern "
            f"'{pattern[:60]}'",
            file=sys.stderr,
        )
        return False
    if error[0] is not None:
        return False
    return result[0]


def load_jsonl_safe(path: str | Path, max_size: int = 10_000_000) -> list[dict]:
    """Safely load a JSONL file with size limit and malformed-line tolerance.

    Reads first, then checks size (avoids TOCTOU race condition).
    Returns a list of parsed JSON objects. Skips malformed lines silently.
    """
    p = Path(path)
    if not p.exists():
        return []
    try:
        raw = p.read_text(encoding="utf-8")
        if len(raw) > max_size:
            return []
        lines = raw.splitlines()
    except OSError:
        return []

    results = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            results.append(json.loads(line))
        except (json.JSONDecodeError, ValueError):
            continue
    return results


# --- Security: Command validation for autonomous execution ---
_COMMAND_BLOCKLIST_PATTERNS = [
    r'\brm\s+(-[a-zA-Z]*[rRf])', r'\bcurl\b', r'\bwget\b', r'\bnc\b', r'\bncat\b',
    r'\bchmod\b', r'\bchown\b', r'\bdd\b', r'\bmkfs\b', r'\bsudo\b',
    r'`[^`]+`',  # backtick execution
    r'\|\s*(ba)?sh\b', r'\|\s*zsh\b',  # pipe to shell
    r'>\s*/dev/', r'>\s*/etc/', r'>\s*/tmp/',  # write to system dirs
    r'\beval\b', r'\bexec\b',
]
# Shell metacharacter patterns — block command chaining and subshells
_COMMAND_METACHAR_PATTERNS = [
    r';\s*\w',        # semicolon chaining
    r'&&\s*\w',       # AND chaining
    r'\|\|\s*\w',     # OR chaining
    r'\$\(',          # command substitution
    r'\n',            # newline injection
]
_COMMAND_BLOCKLIST_RE = [re.compile(p) for p in _COMMAND_BLOCKLIST_PATTERNS]
_COMMAND_METACHAR_RE = [re.compile(p) for p in _COMMAND_METACHAR_PATTERNS]

_COMMAND_ALLOWLIST_PREFIXES = (
    'python3 ', 'python ', 'bash scripts/', 'node ', 'grep ', 'wc ', 'jq ',
    'cat ', 'head ', 'tail ', 'sort ', 'uniq ', 'diff ', 'git ',
    'sh scripts/',
)


def validate_command_safety(cmd: str) -> tuple[bool, str]:
    """Validate a command is safe to run in autonomous mode.

    Returns (is_safe, reason). Always checks blocklist + metacharacters,
    even for allowlisted prefixes. Allowlist is necessary but not sufficient.
    """
    cmd_stripped = cmd.strip()
    if not cmd_stripped:
        return False, "empty command"

    # Always check metacharacters first — blocks command chaining regardless of prefix
    for pattern in _COMMAND_METACHAR_RE:
        if pattern.search(cmd_stripped):
            return False, f"blocked metacharacter: {pattern.pattern}"

    # Check if command starts with an allowed prefix
    is_allowlisted = False
    for prefix in _COMMAND_ALLOWLIST_PREFIXES:
        if cmd_stripped.startswith(prefix):
            is_allowlisted = True
            break

    if not is_allowlisted:
        return False, "command does not match any allowed prefix"

    # Block python -c (arbitrary code execution) even though python3 is allowlisted
    if re.match(r'^python3?\s+-[cmu]', cmd_stripped):
        return False, "blocked: python -c/-m/-u (use script path instead)"

    # Check blocklist even for allowlisted commands
    for pattern in _COMMAND_BLOCKLIST_RE:
        pat_str = pattern.pattern
        # Known false positive: \beval\b in "run-eval.sh", \bexec\b in "exec-task.sh"
        if pat_str in (r'\beval\b', r'\bexec\b'):
            # Only skip for file-path patterns (not -c inline code)
            if re.match(r'^(?:python3?|bash)\s+\S+\.(?:py|sh)', cmd_stripped):
                continue
        if pattern.search(cmd_stripped):
            return False, f"blocked pattern: {pat_str}"

    return True, "allowed prefix"
