"""Pre-compiled regex patterns for all scoring dimensions."""
import re

# --- Used in score_structure() ---
_RE_FRONTMATTER_NAME = re.compile(r"^name:\s*\S+", re.MULTILINE)
_RE_FRONTMATTER_DESC = re.compile(r"^description:", re.MULTILINE)
_RE_REAL_EXAMPLES = re.compile(
    r"(?i)(example\s*[0-9:#]|input.*output|e\.g\.|for instance|for example)"
)
_RE_CODE_BLOCKS = re.compile(r"```")
_RE_HEADERS = re.compile(r"^##\s", re.MULTILINE)
_RE_HEDGING = re.compile(
    r"you (might|could|should|may) (want to|consider|possibly)", re.IGNORECASE
)
_RE_REFS = re.compile(r"(references|scripts|templates)/[\w./-]+")
_RE_TODO = re.compile(r"(?i)(TODO|FIXME|HACK|XXX|placeholder)")
_RE_SECTION_HEADER = re.compile(r"^##\s")

# --- Used in score_efficiency() ---
_RE_ACTIONABLE_LINES = re.compile(
    r"^(?:\d+\.\s*)?(?:Read|Run|Check|Create|Add|Remove|Move|Use|Set|"
    r"Install|Configure|Deploy|Test|Verify|Build|Start|Stop|Open|Save|"
    r"Copy|Delete|Write|Edit|Update|Generate|Execute|Validate|Parse|"
    r"Extract|Transform|Import|Export|Send|Fetch|Call|Return|"
    r"Confirm|Document|List|Show|Print|Log|Review|Apply|Enable|Disable|"
    r"Ensure|Define|Specify|Register|Mount|Scan|Inspect|Monitor)\b",
    re.MULTILINE,
)
_RE_WHY_COUNT = re.compile(
    r"\b(because|since|this enables|this prevents|this means|the reason|"
    r"this ensures|this avoids|otherwise|so that|why[:\s])\b",
    re.IGNORECASE,
)
_RE_VERIFICATION_CMDS = re.compile(r"```\s*(?:bash|sh)\b")
_RE_FILLER_PHRASES = re.compile(
    r"(?i)(it is important to note that|as mentioned (above|earlier|before)|"
    r"in other words|that is to say|keep in mind that|note that|"
    r"it should be noted|please note|remember that|be aware that|"
    r"it's worth mentioning)"
)
_RE_OBVIOUS_INSTRUCTIONS = re.compile(
    r"(?i)(make sure to save|don't forget to|always test your|"
    r"be careful when|ensure you have|make sure you|"
    r"remember to commit|use version control)"
)
_RE_SCOPE_BOUNDARY = re.compile(r"(?i)(do not|don't) use (for|when|if)")

# --- Used in score_composability() ---
_RE_POSITIVE_SCOPE = re.compile(
    r"(?i)(use this skill when|use when|trigger when|activate for)"
)
_RE_NEGATIVE_SCOPE = re.compile(
    r"(?i)(do not use|don't use|NOT for|not use for|out of scope)"
)
_RE_GLOBAL_STATE = re.compile(
    r"(?i)(must be installed globally|global config|~\/\.|modify system|"
    r"system-wide|/etc/|export\s+\w+=)"
)
_RE_INPUT_SPEC = re.compile(
    r"(?i)(input:|takes.*as input|expects|requires.*file|requires.*path|target.*skill)"
)
_RE_OUTPUT_SPEC = re.compile(
    r"(?i)(output:|produces|generates|creates|saves.*to|writes.*to|returns)"
)
_RE_HANDOFF = re.compile(
    r"(?i)(then use|hand off to|pass to|chain with|followed by|"
    r"complementary|works with|after.*use|before.*use|"
    r"skill-creator|next step)"
)
_RE_WHEN_NOT = re.compile(
    r"(?i)(if.*instead use|for.*use.*instead|suggest using)"
)
_RE_HARD_REQUIREMENTS = re.compile(
    r"(?i)(requires?\s+(?:npm|pip|brew|apt|docker|node|python)\b)"
)
_RE_ALTERNATIVES = re.compile(
    r"(?i)(alternatively|or use|if.*not available|fallback)"
)
# New composability patterns (v6.0.1 — granular scoring)
_RE_ERROR_BEHAVIOR = re.compile(
    r"(?i)(on\s+error|error\s+handling|if\s+[\w\s]+\s+fails?|when\s+[\w\s]+\s+fails?|"
    r"graceful(?:ly)?\s+(?:handle|degrad\w+|fail)|recover(?:y|s)?\s+(?:from|when))"
)
_RE_IDEMPOTENCY = re.compile(
    r"(?i)(idempotent|safe to (?:re-?run|run (?:again|twice|multiple))|"
    r"running (?:again|twice)|no side.?effects?|re-?entrant)"
)
_RE_DEPENDENCY_DECL = re.compile(
    r"(?i)(requires?[:\s]+(?:python|node|npm|pip|git|jq|bash|ruby|go)\b|"
    r"depends?\s+on|prerequisite|"
    r"needs?\s+(?:python|node|npm|pip|git|jq|bash|ruby|go)\b|"
    r"install\s+\w+\s+first)"
)
_RE_NAMESPACE_ISOLATION = re.compile(
    r"(?i)(namespace\s+\w+|namespaced?\b|__\w+__|"
    r"@[\w-]+/[\w-]+|plugin[_-]\w+|scoped\s+to\b)"
)
_RE_VERSION_COMPAT = re.compile(
    r"(?i)(version\s*[><=!]+\s*[\d.]+|compatible\s+with\s+\w+\s+v?\d|"
    r"requires?\s+\w+\s*[><=]+\s*[\d.]+|minimum\s+version|"
    r"supported\s+versions?|works\s+with\s+\w+\s+v?\d+\.\d+)"
)

# --- Used in score_clarity() ---
_RE_ALWAYS_PATTERNS = re.compile(r"(?i)\b(always|must)\s+(\w+(?:\s+\w+)?)")
_RE_NEVER_PATTERNS = re.compile(r"(?i)\b(never|must not|do not|don't)\s+(\w+(?:\s+\w+)?)")
_RE_VAGUE_REF = re.compile(
    r"\b(the\s+(?:file|script|output|result|command|path|tool|config))\b", re.IGNORECASE
)
_RE_BACKTICK_REF = re.compile(r"`[^`]+`")
_RE_SPECIFIC_REF = re.compile(r"(`[^`]+`|[\w/]+\.\w+|/[\w/]+)")
_RE_AMBIGUOUS_PRONOUN = re.compile(
    r"^\s*(It|This|That)\s+(is|does|will|can|should|has|was|means)\b"
)
_RE_RUN_PATTERN = re.compile(
    r"^\s*(?:\d+\.\s*)?(?:Run|Execute|Install|Configure)\s+(.+)", re.IGNORECASE
)
_RE_CONCEPTUAL = re.compile(
    r"(?i)(baseline|all\s+\d+|VERIFY|evolution|the\s+\w+\s+(?:on|for|to|with|against))"
)
_RE_CONCRETE_CMD = re.compile(r"(`[^`]+`|[\w/.-]+\.\w+|/[\w/]+)")
_RE_CODE_BLOCK_START = re.compile(r"^```")

# --- Used in score_triggers() / _has_skill_domain_signal() ---
_RE_CREATION_PATTERNS = re.compile(
    r"(?i)(from scratch|brand new|new\b.{0,20}\bskill|create\b.{0,20}\bskill|"
    r"build\b.{0,20}\bskill|write\b.{0,20}\bskill|design\b.{0,20}\bskill)"
)
_RE_NEGATION_BOUNDARIES = re.compile(
    r"(?:do not|don't|NOT|never)\s+(?:use\s+)?(?:for|when|if|with)?\s*(.+?)(?:\.|,|$)",
    re.IGNORECASE,
)

# Domain signal patterns
_RE_STRONG_DOMAIN_SIGNAL = re.compile(
    r"skill\.md|skill\s*forge|my\s+skill|this\s+skill|the\s+skill|"
    r"skill\s+(?:trigger|description|improvement|quality|needs|work)|"
    r"improve\s+(?:my|this|the)\s+skill|"
    r"(?:trigger|eval)\s+(?:accuracy|suite|test)|"
    r"skill\s+(?:and|but|needs|is|has)",
    re.IGNORECASE,
)
_RE_ANTI_DOMAIN_SIGNAL = re.compile(
    r"python\s+function|rest\s+api|docker|"
    r"security\s+vulnerab|\.py\b|\.ts\b|\.js\b|"
    r"open\s+source\s+project|readme|prompt\s+template",
    re.IGNORECASE,
)

# --- Used in score_diff() ---
_RE_DIFF_SIGNAL = re.compile(
    r"^(?:\d+\.\s*)?(?:Read|Run|Check|Create|Add|Remove|Move|Use|Set|"
    r"Install|Configure|Deploy|Test|Verify|Build|Start|Stop|Open|Save|"
    r"Copy|Delete|Write|Edit|Update|Generate|Execute|Validate|Parse|"
    r"Extract|Transform|Import|Export|Send|Fetch|Call|Return)\b",
    re.IGNORECASE,
)
_RE_DIFF_EXAMPLE = re.compile(
    r"(?i)(example\s*[0-9:#]|input.*output|e\.g\.|for instance|for example)"
)
_RE_DIFF_NOISE = re.compile(
    r"(?i)(you (might|could|should|may) (want to|consider|possibly)|"
    r"it is important to note that|as mentioned (above|earlier|before)|"
    r"in other words|keep in mind that|note that|please note|"
    r"make sure to save|don't forget to|always test your)"
)

# --- Used in score_coherence() ---
_RE_IMPERATIVE_INSTRUCTION = re.compile(
    r"^\s*(?:\d+\.\s*)?(?:Run|Create|Add|Check|Remove|Move|Use|Set|Install|"
    r"Configure|Deploy|Test|Verify|Build|Start|Stop|Open|Save|Copy|Delete|"
    r"Write|Edit|Update|Generate|Execute|Validate|Parse|Extract|Transform|"
    r"Import|Export|Send|Fetch|Call|Return)\b(.+)",
    re.IGNORECASE,
)
_RE_CODE_BLOCK_REGION = re.compile(r"```[\s\S]*?```")


def _has_skill_domain_signal(prompt: str) -> float:
    """Check if prompt is about skills (not generic code/config).

    Returns a multiplier: 1.8 for strong signal, 1.0 for neutral, 0.4 for anti-signal.
    """
    prompt_lower = prompt.lower()

    if _RE_STRONG_DOMAIN_SIGNAL.search(prompt_lower):
        return 1.8

    if "skill" in prompt_lower:
        return 1.2

    if _RE_ANTI_DOMAIN_SIGNAL.search(prompt_lower):
        return 0.4

    return 1.0
