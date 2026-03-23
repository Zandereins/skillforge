#!/usr/bin/env python3
"""SkillForge — Shared Utilities

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
    """
    p = Path(skill_path).resolve()
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


def load_eval_suite(skill_path: str) -> Optional[dict]:
    """Auto-discover and load eval-suite.json from skill directory."""
    skill_dir = Path(skill_path).parent
    auto_path = skill_dir / "eval-suite.json"
    if auto_path.exists():
        try:
            return json.loads(auto_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(f"Warning: malformed eval-suite.json: {e}", file=sys.stderr)
    return None


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
_COMMAND_BLOCKLIST_RE = [re.compile(p) for p in _COMMAND_BLOCKLIST_PATTERNS]

_COMMAND_ALLOWLIST_PREFIXES = (
    'python3 ', 'python ', 'bash scripts/', 'node ', 'grep ', 'wc ', 'jq ',
    'cat ', 'head ', 'tail ', 'sort ', 'uniq ', 'diff ', 'git ',
    'sh scripts/',
)


def validate_command_safety(cmd: str) -> tuple[bool, str]:
    """Validate a command is safe to run in autonomous mode.

    Returns (is_safe, reason). Checks allowlist first, then blocklist.
    """
    cmd_stripped = cmd.strip()
    if not cmd_stripped:
        return False, "empty command"

    # Check allowlist FIRST (prevents false positives like "run-eval.sh" matching \beval\b)
    for prefix in _COMMAND_ALLOWLIST_PREFIXES:
        if cmd_stripped.startswith(prefix):
            return True, "allowed prefix"

    # Check blocklist
    for pattern in _COMMAND_BLOCKLIST_RE:
        if pattern.search(cmd_stripped):
            return False, f"blocked pattern: {pattern.pattern}"

    return False, "command does not match any allowed prefix"
