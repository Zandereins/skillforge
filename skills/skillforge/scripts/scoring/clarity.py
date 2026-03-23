"""Score instruction clarity — detect contradictions, ambiguity, vague references.

Optional 7th dimension with zero default weight. Activated via --clarity.

Sub-checks (100 pts total):
- Contradiction detection (30 pts): "always X" vs "never X" on same topic
- Vague reference detection (25 pts): "the file" without antecedent
- Ambiguous pronoun detection (20 pts): sentences starting with It/This/That
- Instruction completeness (25 pts): every "Run X" has a concrete command
"""
from shared import read_skill_safe, strip_frontmatter
from scoring.patterns import (
    _RE_ALWAYS_PATTERNS, _RE_NEVER_PATTERNS, _RE_VAGUE_REF,
    _RE_BACKTICK_REF, _RE_SPECIFIC_REF, _RE_AMBIGUOUS_PRONOUN,
    _RE_RUN_PATTERN, _RE_CONCEPTUAL, _RE_CONCRETE_CMD,
    _RE_CODE_BLOCK_REGION,
)


def score_clarity(skill_path: str) -> dict:
    """Score instruction clarity — detect contradictions, ambiguity, vague references.

    Optional 7th dimension with zero default weight. Activated via --clarity.

    Sub-checks (100 pts total):
    - Contradiction detection (30 pts): "always X" vs "never X" on same topic
    - Vague reference detection (25 pts): "the file" without antecedent
    - Ambiguous pronoun detection (20 pts): sentences starting with It/This/That
    - Instruction completeness (25 pts): every "Run X" has a concrete command
    """
    try:
        content = read_skill_safe(skill_path)
    except (FileNotFoundError, ValueError):
        return {"score": 0, "issues": ["file_not_found"], "details": {}}

    # Strip frontmatter
    body = strip_frontmatter(content)

    # Strip code blocks before clarity analysis (avoid false positives
    # from "always"/"never" inside code examples)
    prose_body = _RE_CODE_BLOCK_REGION.sub("", body)

    lines = prose_body.strip().split("\n")

    # Empty body check
    if not prose_body.strip():
        return {"score": 0, "issues": ["empty_skill_body"], "details": {}}

    score = 100
    issues = []
    details: dict = {}

    # 1. Contradiction detection (30 pts)
    # Find "always/never/must/must not" pairs on overlapping topics
    # Compare first verb only to catch "always run X" vs "never run Y"
    always_patterns = _RE_ALWAYS_PATTERNS.findall(prose_body)
    never_patterns = _RE_NEVER_PATTERNS.findall(prose_body)

    always_topics = {topic.lower().strip() for _, topic in always_patterns}
    never_topics = {topic.lower().strip() for _, topic in never_patterns}
    contradictions = always_topics & never_topics

    if contradictions:
        penalty = min(30, len(contradictions) * 10)
        score -= penalty
        issues.append(f"contradictions:{len(contradictions)}")
        details["contradictions"] = sorted(contradictions)
    details["always_count"] = len(always_patterns)
    details["never_count"] = len(never_patterns)

    # 2. Vague reference detection (25 pts)
    # "the file", "the script", "the output" without clear antecedent in preceding 3 lines
    vague_refs = []
    for i, line in enumerate(lines):
        matches = _RE_VAGUE_REF.findall(line)
        for match in matches:
            # Skip if backtick-quoted reference is on the same line (e.g., "the file `output.json`")
            if _RE_BACKTICK_REF.search(line):
                continue
            # Check preceding 3 lines for a specific file/path reference
            context = "\n".join(lines[max(0, i - 3):i])
            # If no specific path, filename, or backtick-quoted reference nearby, it's vague
            if not _RE_SPECIFIC_REF.search(context):
                vague_refs.append(f"line {i + 1}: {match}")

    if vague_refs:
        penalty = min(25, len(vague_refs) * 5)
        score -= penalty
        issues.append(f"vague_references:{len(vague_refs)}")
    details["vague_references"] = len(vague_refs)

    # 3. Ambiguous pronoun detection (20 pts)
    # Sentences starting with "It ", "This ", "That " without clear referent
    ambiguous_pronouns = []
    for i, line in enumerate(lines):
        if _RE_AMBIGUOUS_PRONOUN.match(line):
            # Check if preceding line provides a clear subject
            if i > 0:
                prev = lines[i - 1].strip()
                # If previous line is empty or a header, the pronoun is ambiguous
                if not prev or prev.startswith("#"):
                    ambiguous_pronouns.append(f"line {i + 1}")

    if ambiguous_pronouns:
        penalty = min(20, len(ambiguous_pronouns) * 5)
        score -= penalty
        issues.append(f"ambiguous_pronouns:{len(ambiguous_pronouns)}")
    details["ambiguous_pronouns"] = len(ambiguous_pronouns)

    # 4. Instruction completeness (25 pts)
    # Every "Run X" / "Execute X" should have a concrete command or path
    # Skip conceptual uses like "Run eval evolution BETWEEN sessions"
    incomplete_instructions = []
    for i, line in enumerate(lines):
        m = _RE_RUN_PATTERN.match(line)
        if m:
            rest = m.group(1).strip()
            # Skip conceptual instructions (not meant as shell commands)
            if _RE_CONCEPTUAL.search(rest):
                continue
            # Check if there's a backtick command, a path, or a code block nearby
            has_concrete = bool(_RE_CONCRETE_CMD.search(rest))
            # Also check next line for a code block
            if not has_concrete and i + 1 < len(lines):
                has_concrete = lines[i + 1].strip().startswith("```")
            if not has_concrete:
                incomplete_instructions.append(f"line {i + 1}: {line.strip()[:60]}")

    if incomplete_instructions:
        penalty = min(25, len(incomplete_instructions) * 8)
        score -= penalty
        issues.append(f"incomplete_instructions:{len(incomplete_instructions)}")
    details["incomplete_instructions"] = len(incomplete_instructions)

    return {
        "score": max(0, score),
        "issues": issues,
        "details": details,
    }
