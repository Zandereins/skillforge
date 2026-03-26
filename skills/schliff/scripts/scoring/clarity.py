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


_ARTICLES = frozenset({"the", "a", "an", "this", "that", "any", "all"})


def _extract_action_pairs(text, pattern):
    """Extract (verb, object, modifier) tuples from instruction patterns.

    For "Always run the linter" → ("run", "linter", "").
    For "Never run tests in production" → ("run", "tests", "production").
    Articles between verb and object are skipped so that
    "run the linter" and "run linter" both yield ("run", "linter", "").

    The modifier captures context words after the object (e.g., "in production",
    "without coverage") to distinguish instructions that share the same verb+object
    but apply to different contexts. Only words on the same line are considered.
    """
    pairs = set()
    for match in pattern.finditer(text):
        topic = match.group(2).strip().split()
        verb = topic[0].lower().rstrip(".,;:!?")
        # Only use words from the same line as context (not cross-line)
        line_end = text.find("\n", match.end())
        if line_end == -1:
            line_end = len(text)
        rest_of_line = text[match.end():line_end].strip().split()
        candidates = topic[1:] + rest_of_line[:4]
        obj_candidates = [
            w.lower().rstrip(".,;:!?") for w in candidates
            if w.lower().rstrip(".,;:!?") not in _ARTICLES and w.lower().rstrip(".,;:!?")
        ]
        if obj_candidates:
            obj_word = obj_candidates[0]
            # Capture modifier: first non-article word after the object for context
            modifier_candidates = [
                w for w in obj_candidates[1:]
                if w not in _ARTICLES
            ]
            modifier = modifier_candidates[0] if modifier_candidates else ""
            pairs.add((verb, obj_word, modifier))
    return pairs


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
    # Extract (verb, object) pairs from "always/must" vs "never/must not" patterns.
    # A contradiction exists when the same (verb, object) pair appears in both.
    always_pairs = _extract_action_pairs(prose_body, _RE_ALWAYS_PATTERNS)
    never_pairs = _extract_action_pairs(prose_body, _RE_NEVER_PATTERNS)
    contradictions = always_pairs & never_pairs

    if contradictions:
        penalty = min(30, len(contradictions) * 10)
        score -= penalty
        issues.append(f"contradictions:{len(contradictions)}")
        details["contradictions"] = sorted(
            f"{verb} {obj}" for verb, obj, *_ in contradictions
        )
    details["always_count"] = len(always_pairs)
    details["never_count"] = len(never_pairs)

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
            if i == 0:
                # First line has no preceding context — pronoun is ambiguous
                ambiguous_pronouns.append(f"line {i + 1}")
            else:
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
