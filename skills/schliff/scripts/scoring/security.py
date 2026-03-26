"""Score security dimension of a skill file.

Deductive scoring: starts at 100, subtracts penalties for each security
anti-pattern found. Implements three false-positive mitigation mechanisms:
code-block exclusion, meta-discourse detection, and negation-aware matching.
"""
from __future__ import annotations

import re
from typing import Optional

from shared import read_skill_safe
from scoring.patterns import (
    _RE_SEC_PROMPT_INJECTION,
    _RE_SEC_INSTRUCTION_OVERRIDE,
    _RE_SEC_DATA_EXFIL,
    _RE_SEC_ENV_LEAK,
    _RE_SEC_DANGEROUS_CMD,
    _RE_SEC_BASE64_CMD,
    _RE_SEC_ZERO_WIDTH,
    _RE_SEC_HEX_ESCAPE,
    _RE_SEC_OVERPERMISSION,
    _RE_SEC_BOUNDARY_VIOLATION,
    _RE_CODE_BLOCK_REGION,
)

# ---------------------------------------------------------------------------
# Pattern categories: (category_name, penalty_per_match, [compiled_patterns])
# ---------------------------------------------------------------------------
_CATEGORIES: list[tuple[str, int, list[re.Pattern]]] = [
    ("injection", 25, [_RE_SEC_PROMPT_INJECTION, _RE_SEC_INSTRUCTION_OVERRIDE]),
    ("exfil", 25, [_RE_SEC_DATA_EXFIL, _RE_SEC_ENV_LEAK]),
    ("dangerous_cmd", 20, [_RE_SEC_DANGEROUS_CMD]),
    ("obfuscation", 15, [_RE_SEC_BASE64_CMD, _RE_SEC_ZERO_WIDTH, _RE_SEC_HEX_ESCAPE]),
    ("overpermission", 15, [_RE_SEC_OVERPERMISSION]),
    ("boundaries", 10, [_RE_SEC_BOUNDARY_VIOLATION]),
]

# ---------------------------------------------------------------------------
# Meta-discourse detection keywords
# ---------------------------------------------------------------------------
_META_DESC_KEYWORDS = re.compile(
    r"(?i)\b(security|vulnerability|vulnerabilities|pentest|penetration\s+test|"
    r"CVE|OWASP|exploit|threat|malware)\b"
)
_META_NAME_KEYWORDS = re.compile(
    r"(?i)(security|vuln|shield|guard|sentinel)"
)

# ---------------------------------------------------------------------------
# Negation words for negation-aware matching
# ---------------------------------------------------------------------------
_NEGATION_RE = re.compile(
    r"(?i)\b(never|don't|do not|avoid|must not|should not|shouldn't|"
    r"not|won't|cannot|can't)\b"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_frontmatter(content: str) -> str:
    """Return raw YAML frontmatter string (without delimiters), or ''."""
    if content.startswith("---"):
        end = content.find("---", 3)
        if end >= 4:
            return content[3:end]
    return ""


def _is_security_domain(content: str) -> bool:
    """Detect whether the skill is about security (educational content)."""
    fm = _extract_frontmatter(content)
    if not fm:
        return False

    # Check description field
    desc_match = re.search(r"(?m)^description:.*?(?=^\S|\Z)", fm, re.DOTALL)
    if desc_match and _META_DESC_KEYWORDS.search(desc_match.group()):
        return True

    # Check metadata.domain: security
    if re.search(r"(?m)domain:\s*security", fm, re.IGNORECASE):
        return True

    # Check name field
    name_match = re.search(r"(?m)^name:\s*(.+)", fm)
    if name_match and _META_NAME_KEYWORDS.search(name_match.group(1)):
        return True

    return False


def _find_code_block_ranges(content: str) -> list[tuple[int, int]]:
    """Return list of (start, end) positions for ```...``` code blocks."""
    return [(m.start(), m.end()) for m in _RE_CODE_BLOCK_REGION.finditer(content)]


def _in_code_block(pos: int, ranges: list[tuple[int, int]]) -> bool:
    """Check if a character position falls inside any code block range."""
    for start, end in ranges:
        if start <= pos < end:
            return True
    return False


def _preceded_by_negation(content: str, match_start: int) -> bool:
    """Check if the ~50 chars before match_start contain a negation word."""
    window_start = max(0, match_start - 50)
    window = content[window_start:match_start]
    return bool(_NEGATION_RE.search(window))


# ---------------------------------------------------------------------------
# Main scorer
# ---------------------------------------------------------------------------

def score_security(skill_path: str) -> dict:
    """Score security dimension of a skill file.

    Deductive scoring: starts at 100, subtracts penalties for each security
    anti-pattern found. Implements three false-positive mitigation mechanisms:
    code-block exclusion, meta-discourse detection, and negation-aware matching.

    Returns:
        {
            "score": int (0-100, clamped),
            "issues": list[str],
            "details": {
                "category_penalties": dict,
                "total_penalty": int,
                "meta_discourse_reduction": float,
                "code_block_excluded": int,
                "negation_excluded": int,
            }
        }
    """
    content = read_skill_safe(skill_path)

    # Meta-discourse detection
    is_security = _is_security_domain(content)
    meta_reduction = 0.1 if is_security else 1.0

    # Code block ranges
    cb_ranges = _find_code_block_ranges(content)

    # Scan all categories
    category_penalties: dict[str, float] = {}
    issues: list[str] = []
    code_block_excluded = 0
    negation_excluded = 0

    for cat_name, penalty_per_match, patterns in _CATEGORIES:
        cat_raw = 0
        for pat in patterns:
            for m in pat.finditer(content):
                match_start = m.start()

                # Code-block exclusion (not for obfuscation)
                if cat_name != "obfuscation" and _in_code_block(match_start, cb_ranges):
                    code_block_excluded += 1
                    continue

                # Negation-aware exclusion (all categories)
                if _preceded_by_negation(content, match_start):
                    negation_excluded += 1
                    continue

                cat_raw += penalty_per_match

        if cat_raw > 0:
            category_penalties[cat_name] = cat_raw

    # Apply meta-discourse reduction
    total_penalty = 0.0
    for cat_name in category_penalties:
        category_penalties[cat_name] = category_penalties[cat_name] * meta_reduction
        total_penalty += category_penalties[cat_name]

    total_penalty_int = int(round(total_penalty))
    score = max(0, 100 - total_penalty_int)

    # Build issues list
    for cat_name in category_penalties:
        if category_penalties[cat_name] > 0:
            issues.append(f"security:{cat_name}")

    return {
        "score": score,
        "issues": issues,
        "details": {
            "category_penalties": category_penalties,
            "total_penalty": total_penalty_int,
            "meta_discourse_reduction": meta_reduction,
            "code_block_excluded": code_block_excluded,
            "negation_excluded": negation_excluded,
        },
    }


def get_composite_cap(security_score: int) -> Optional[int]:
    """Return composite score cap based on security score, or None if no cap."""
    if security_score < 5:
        return 20
    if security_score < 10:
        return 40
    if security_score < 20:
        return 60
    return None
