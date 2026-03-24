"""Score token efficiency — information density.

Measures how much useful, actionable content the skill delivers
relative to its total size. Penalizes bloat, rewards conciseness.
"""
from shared import read_skill_safe, strip_frontmatter
from scoring.patterns import (
    _RE_ACTIONABLE_LINES, _RE_REAL_EXAMPLES, _RE_WHY_COUNT,
    _RE_VERIFICATION_CMDS, _RE_HEDGING, _RE_FILLER_PHRASES,
    _RE_OBVIOUS_INSTRUCTIONS, _RE_SCOPE_BOUNDARY,
    _RE_CODE_BLOCK_REGION,
)


def score_efficiency(skill_path: str) -> dict:
    """Score token efficiency — information density.

    Measures how much useful, actionable content the skill delivers
    relative to its total size. Penalizes bloat, rewards conciseness.

    Key insight: A good efficiency metric should NOT reward adding more
    headers or code blocks. It should reward delivering more value in
    fewer words.
    """
    try:
        content = read_skill_safe(skill_path)
    except (FileNotFoundError, ValueError):
        return {"score": 0, "issues": ["file_not_found"], "details": {}}

    full_content = content

    # Strip frontmatter for body analysis
    content = strip_frontmatter(content)

    lines = content.strip().split("\n")
    total_lines = len(lines)
    words = content.split()
    total_words = len(words)

    if total_words == 0:
        return {"score": 0, "issues": ["empty_skill_body"], "details": {}}

    # --- Signal indicators (what makes content valuable) ---

    # Actionable instructions (imperative verbs at line start)
    # Deduplicate on full line content: repeated identical instructions are noise.
    # Truncate to 80 chars to catch near-duplicates while preserving distinct instructions.
    seen_actions = set()
    for line in lines:
        if _RE_ACTIONABLE_LINES.match(line.strip()):
            key = line.strip().lower()[:80]
            seen_actions.add(key)
    actionable_lines = len(seen_actions)

    # Real examples (input/output pairs, not just code blocks)
    real_examples = len(_RE_REAL_EXAMPLES.findall(content))

    # WHY-based reasoning (explains rationale)
    why_count = len(_RE_WHY_COUNT.findall(content))

    # Verification commands (executable checks)
    verification_cmds = len(_RE_VERIFICATION_CMDS.findall(content))

    # --- Noise indicators (what wastes tokens) ---

    # Hedging language
    hedge_count = len(_RE_HEDGING.findall(content))

    # Redundant phrases (saying the same thing multiple ways)
    filler_phrases = len(_RE_FILLER_PHRASES.findall(content))

    # Instructions Claude already knows (generic coding advice)
    obvious_instructions = len(_RE_OBVIOUS_INSTRUCTIONS.findall(content))

    # Repeated identical lines (content padding)
    # Lines appearing 3+ times are noise — they add words without new information.
    # Strip code blocks first (repeated code examples are often didactic, not padding).
    # Exclude structural markers that naturally repeat in well-formed skills.
    prose_content = _RE_CODE_BLOCK_REGION.sub("", content)
    prose_lines = prose_content.strip().split("\n")
    line_counts: dict[str, int] = {}
    for line in prose_lines:
        key = line.strip().lower()
        if not key:
            continue
        # Skip structural markers that legitimately repeat
        if (key.startswith("```")           # code block fences (residual)
                or key.startswith("---")    # horizontal rules / frontmatter
                or key.startswith("#")      # headers
                or len(key) <= 3):          # very short tokens (e.g. "/foo")
            continue
        line_counts[key] = line_counts.get(key, 0) + 1
    repeated_lines = sum(count - 1 for count in line_counts.values() if count >= 3)

    # Empty/near-empty lines ratio
    empty_lines = sum(1 for line in lines if not line.strip())
    empty_ratio = empty_lines / max(total_lines, 1)

    # --- Compute score ---

    # Base score: information density (signal words / total words)
    # Caps prevent gaming via repetitive markers (e.g., 10x "for example")
    signal_count = (
        min(actionable_lines, 20) * 3 +  # High value: direct instructions
        min(real_examples, 3) * 5 +       # High value: concrete examples (capped)
        min(why_count, 5) * 2 +           # Medium value: reasoning
        min(verification_cmds, 5) * 2     # Medium value: verifiable steps
    )
    noise_count = (
        hedge_count * 3 +
        filler_phrases * 2 +
        obvious_instructions * 2 +
        repeated_lines * 2           # Repeated identical lines are padding
    )

    # Density = signal per 100 words, penalized by noise
    density = ((signal_count - noise_count) / max(total_words, 1)) * 100

    # Map density to score — continuous (no step-function cliffs).
    # Uses sqrt curve calibrated to match previous step midpoints:
    #   density 0→40, 0.5→52, 1.5→61, 3→70, 5→79, 8→89, 10→95
    if density <= 0:
        score = 40
    elif density >= 10:
        score = 95
    else:
        score = 40 + (density / 10) ** 0.5 * 55
    score = min(95, max(40, score))

    # Penalty for excessive length without proportional signal
    if total_words > 2000 and density < 3:
        score = max(20, score - 15)

    # Penalty for too much whitespace (padding)
    if empty_ratio > 0.3:
        score = max(20, score - 5)

    # Bonus for explicit scope boundaries (+3)
    if _RE_SCOPE_BOUNDARY.search(full_content):
        score = min(100, score + 3)

    # Bonus for conciseness: under 300 lines with good signal (+5)
    if total_lines <= 300 and density >= 3:
        score = min(100, score + 5)

    issues = []
    if hedge_count > 2:
        issues.append(f"excessive_hedging:{hedge_count}")
    if filler_phrases > 2:
        issues.append(f"filler_phrases:{filler_phrases}")
    if obvious_instructions > 1:
        issues.append(f"obvious_instructions:{obvious_instructions}")
    if total_words > 2000:
        issues.append(f"verbose:{total_words}_words")
    if repeated_lines > 3:
        issues.append(f"repeated_lines:{repeated_lines}")

    return {
        "score": min(100, max(0, score)),
        "issues": issues,
        "details": {
            "total_words": total_words,
            "total_lines": total_lines,
            "signal_count": signal_count,
            "noise_count": noise_count,
            "density": round(density, 2),
            "actionable_lines": actionable_lines,
            "real_examples": real_examples,
            "why_count": why_count,
            "hedge_count": hedge_count,
            "filler_phrases": filler_phrases,
            "repeated_lines": repeated_lines,
        }
    }
