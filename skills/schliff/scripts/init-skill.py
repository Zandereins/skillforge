#!/usr/bin/env python3
"""Schliff — Eval-Suite Bootstrapper

Reads a SKILL.md file, auto-generates an eval-suite.json with triggers +
test cases, runs baseline scoring, and outputs a summary.

No LLM calls — pure heuristics.

Usage:
    python3 init-skill.py /path/to/SKILL.md [--json] [--dry-run] [--output PATH]

Exit codes:
    0 = success
    1 = error (file not found, parse error, etc.)
    2 = argparse error (handled by argparse itself)
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

# Maximum skill file size: 1 MB
MAX_SKILL_SIZE = 1_000_000

SCRIPT_DIR = Path(__file__).parent

# Import terminal_art for grade system and score cards
from terminal_art import score_to_grade, grade_colored, colored_bar, is_color_tty

# Action verb phrases extracted from imperative sentences in descriptions
_ACTION_VERBS = [
    "improve", "optimize", "audit", "benchmark", "harden", "analyze",
    "iterate", "refine", "review", "grind", "fix", "enhance",
]

# Generic negative trigger prompts that should never activate a skill-specific tool
_GENERIC_NEGATIVES = [
    "Can you review this Python function for bugs?",
    "Help me set up CI/CD for my repository",
    "Write me a unit test for this class",
    "Refactor this module to use dependency injection",
    "Debug why my API returns a 500 error",
]


# ---------------------------------------------------------------------------
# Description-aware domain extraction
# ---------------------------------------------------------------------------

def _extract_skill_purpose(desc: str, content: str) -> dict:
    """Extract the skill's domain and purpose from its description and content.

    Returns {"actions": [...], "use_when": [...], "domain_terms": [...]}.
    Actions are verb-phrase strings describing what the skill does (e.g. "review code").
    """
    actions: list[str] = []
    use_when: list[str] = []
    domain_terms: list[str] = []
    seen = set()

    def _add_action(s: str) -> None:
        s = s.strip().rstrip(".,;")
        if s and s.lower() not in seen and 3 < len(s) < 80:
            seen.add(s.lower())
            actions.append(s)

    def _add_use_when(s: str) -> None:
        s = s.strip().rstrip(".,;")
        if s and len(s) > 5:
            use_when.append(s)

    combined = f"{desc}\n{content}" if content else desc

    # 1. "Use when ..." / "Trigger when ..." clauses → direct usage scenarios
    for m in re.finditer(
        r"(?:Use when|Trigger when|Invoke when|Activate (?:for|when))\s+(.+?)(?:\.|$)",
        combined, re.IGNORECASE | re.MULTILINE,
    ):
        _add_use_when(m.group(1))

    # 2. "<tool/framework/system/agent> for <purpose>" pattern
    for m in re.finditer(
        r"(?:tool|framework|system|agent|bot|helper|utility|plugin|skill)\s+(?:for|that)\s+(.+?)(?:\.|,|$)",
        desc, re.IGNORECASE,
    ):
        _add_action(m.group(1))

    # 3. Verb-object phrases from description (e.g. "reviews code", "generates tests")
    for m in re.finditer(
        r"\b((?:review|generate|create|analyze|test|deploy|debug|build|scan|lint|format|check|validate|monitor|detect|transform|convert|parse|extract|migrate|refactor|optimize|evaluate|measure|benchmark|score|audit|inspect|secure|harden|document|translate|compile|render|simulate|visualize|export|import|publish|sync|backup|restore|index|search|query|route|filter|aggregate|classify|annotate|summarize|explain|compare|diff|merge|rebase|cherry-pick|bisect|blame|log|trace|profile|serialize|deserialize|encode|decode|encrypt|decrypt|sign|verify|authenticate|authorize)(?:s|es|ed|ing)?\s+(?:the\s+)?[\w\s-]{2,40}?)\b",
        desc, re.IGNORECASE,
    ):
        candidate = m.group(1).strip()
        # Skip overly long or noisy matches
        if len(candidate.split()) <= 6:
            _add_action(candidate)

    # 4. Extract quoted examples from description ("like this")
    for m in re.finditer(r'["\']([^"\']{5,60})["\']', desc):
        phrase = m.group(1).strip()
        if any(c.isalpha() for c in phrase):
            _add_action(phrase)

    # 5. Domain-specific nouns (used for negative trigger differentiation)
    domain_noun_re = re.compile(
        r"\b((?:code|security|performance|accessibility|api|database|test|frontend|backend|"
        r"infrastructure|deployment|monitoring|logging|authentication|authorization|"
        r"review|PR|pull request|commit|branch|merge|CI|CD|pipeline|container|"
        r"docker|kubernetes|terraform|ansible|migration|schema|query|endpoint|"
        r"webhook|event|message|notification|email|chat|bot|agent|workflow|"
        r"template|component|module|package|dependency|vulnerability|compliance|"
        r"documentation|markdown|yaml|json|config|environment)\s*\w*)\b",
        re.IGNORECASE,
    )
    for m in domain_noun_re.finditer(desc):
        term = m.group(1).strip().lower()
        if term not in domain_terms:
            domain_terms.append(term)

    return {"actions": actions, "use_when": use_when, "domain_terms": domain_terms}


# ---------------------------------------------------------------------------
# Frontmatter parsing
# ---------------------------------------------------------------------------

def parse_frontmatter(content: str) -> dict:
    """Extract name and description from YAML frontmatter.

    Supports:
      - Inline values:   name: my-skill
      - Block scalar >:  multi-line folded (newlines become spaces)
      - Block scalar |:  multi-line literal (newlines preserved)

    Does NOT use pyyaml — pure regex.

    Returns {"name": str, "description": str}.
    """
    name = ""
    description = ""

    # Locate frontmatter block between first and second --- markers
    fm_match = re.match(r"^---\r?\n(.*?)\r?\n---", content, re.DOTALL)
    if not fm_match:
        return {"name": name, "description": description}

    fm_block = fm_match.group(1)

    # Extract name (always inline)
    name_match = re.search(r"^name:\s*(.+)$", fm_block, re.MULTILINE)
    if name_match:
        name = name_match.group(1).strip().strip('"\'')

    # Extract description — detect inline, block scalar >, or block scalar |
    desc_match = re.search(
        r"^description:\s*(.*?)(?=\n\S|\Z)", fm_block, re.MULTILINE | re.DOTALL
    )
    if desc_match:
        raw = desc_match.group(1)

        # Block scalar: starts with > or | on the same line or immediately after key
        if re.match(r"^\s*[>|]", raw):
            # Collect indented continuation lines
            # Find the leading indent of the first content line
            lines = raw.splitlines()
            # First line may be just ">" or "|" with optional trailing content
            scalar_indicator = lines[0].strip() if lines else ""
            content_lines = []
            base_indent = None
            for line in lines[1:]:
                if line.strip() == "":
                    content_lines.append("")
                    continue
                stripped = line.lstrip()
                indent = len(line) - len(stripped)
                if base_indent is None:
                    base_indent = indent
                if indent >= (base_indent or 0):
                    content_lines.append(stripped)
                else:
                    break

            if "|" in scalar_indicator:
                # Literal: preserve newlines
                description = "\n".join(content_lines).strip()
            else:
                # Folded (>): collapse newlines into spaces
                description = " ".join(
                    line if line else "\n" for line in content_lines
                ).strip()
        else:
            # Inline value — may span continuation lines (indented)
            raw_lines = raw.splitlines()
            parts = []
            for line in raw_lines:
                s = line.strip()
                if s:
                    parts.append(s)
            description = " ".join(parts).strip().strip('"\'')

    return {"name": name, "description": description}


# ---------------------------------------------------------------------------
# Trigger phrase extraction
# ---------------------------------------------------------------------------

def extract_trigger_phrases(content: str) -> list[str]:
    """Extract trigger phrases from SKILL.md content.

    Looks for:
      1. Lines matching "Use when", "Trigger when", "Activate for", "Invoke when"
      2. Quoted phrases ("like this" or 'like this')
      3. Lines after "Trigger phrases:" header
      4. Action verb phrases from description verbs

    Returns a deduplicated list of strings.
    """
    phrases: list[str] = []
    seen: set[str] = set()

    def _add(phrase: str) -> None:
        p = phrase.strip().strip('"\'').strip()
        if p and p.lower() not in seen:
            seen.add(p.lower())
            phrases.append(p)

    lines = content.splitlines()

    # 1. Lines starting with trigger keywords
    trigger_line_re = re.compile(
        r"^\s*(?:Use when|Trigger when|Activate for|Invoke when)[:\s]+(.+)$",
        re.IGNORECASE,
    )
    for line in lines:
        m = trigger_line_re.match(line)
        if m:
            _add(m.group(1))

    # 2. Quoted phrases (double or single quotes, at least 4 chars)
    quoted_re = re.compile(r'["\']([^"\']{4,})["\']')
    for m in quoted_re.finditer(content):
        _add(m.group(1))

    # 3. Lines after "Trigger phrases:" header (until blank line or next header)
    in_trigger_section = False
    for line in lines:
        if re.match(r"^\s*Trigger phrases?:", line, re.IGNORECASE):
            in_trigger_section = True
            # Inline content after the colon
            inline = re.sub(r"^\s*Trigger phrases?:\s*", "", line, flags=re.IGNORECASE)
            for phrase in re.split(r",\s*", inline):
                _add(phrase)
            continue
        if in_trigger_section:
            if line.strip() == "" or re.match(r"^#+\s", line):
                in_trigger_section = False
                continue
            # Strip list markers
            phrase = re.sub(r"^\s*[-*]\s*", "", line).strip()
            for part in re.split(r",\s*", phrase):
                _add(part)

    # 4. Action verb phrases from the content itself
    for verb in _ACTION_VERBS:
        verb_re = re.compile(
            rf"\b({verb}\s+(?:my\s+)?[\w\s-]{{3,30}}?)\b",
            re.IGNORECASE,
        )
        for m in verb_re.finditer(content):
            candidate = m.group(1).strip()
            # Skip if too long or contains structural noise
            if len(candidate.split()) <= 6:
                _add(candidate)

    return phrases


# ---------------------------------------------------------------------------
# Trigger generation helpers
# ---------------------------------------------------------------------------

def _slugify(name: str) -> str:
    """Return a human-readable skill name for use in prompt text."""
    return name.replace("-", " ").replace("_", " ")


def generate_positive_triggers(
    name: str, desc: str, phrases: list[str], content: str = ""
) -> list[dict]:
    """Generate 5–8 positive trigger test cases.

    Uses description-aware generation: triggers match the skill's actual
    domain, not Schliff's domain.  Falls back to name-based generic prompts
    only when the description yields insufficient material.
    """
    slug = _slugify(name)
    triggers: list[dict] = []

    purpose = _extract_skill_purpose(desc, content)

    # Tier 1: From "Use when" / "Trigger when" clauses (highest quality)
    for phrase in purpose["use_when"][:3]:
        triggers.append({
            "id": f"pos-{len(triggers) + 1}",
            "prompt": phrase if len(phrase) > 15 else f"Can you {phrase.lower()}?",
            "should_trigger": True,
            "category": "positive",
            "notes": f"From 'Use when' clause in SKILL.md",
        })

    # Tier 2: From extracted action phrases (description-derived)
    for action in purpose["actions"][:3]:
        if len(triggers) >= 6:
            break
        triggers.append({
            "id": f"pos-{len(triggers) + 1}",
            "prompt": f"Can you {action.lower()} for me?",
            "should_trigger": True,
            "category": "positive",
            "notes": f"Derived from description action: \"{action}\"",
        })

    # Tier 3: From trigger-phrase extraction (existing logic)
    for phrase in phrases[:3]:
        if len(triggers) >= 7:
            break
        # Skip if we already generated a very similar trigger
        prompt = f"Can you {phrase.lower()} for my {slug} skill?"
        if any(phrase.lower()[:20] in t["prompt"].lower() for t in triggers):
            continue
        triggers.append({
            "id": f"pos-{len(triggers) + 1}",
            "prompt": prompt,
            "should_trigger": True,
            "category": "positive",
            "notes": f"Derived from extracted phrase: \"{phrase}\"",
        })

    # Tier 4: Generic name-based fallbacks (domain-neutral, NOT schliff-specific)
    generic_prompts = [
        (f"I need help with {slug}", "Name-based request"),
        (f"Can you run {slug} on this?", "Direct invocation"),
        (f"Use {slug} to help me with this task", "Explicit skill reference"),
    ]
    for prompt_text, note in generic_prompts:
        if len(triggers) >= 8:
            break
        triggers.append({
            "id": f"pos-{len(triggers) + 1}",
            "prompt": prompt_text,
            "should_trigger": True,
            "category": "positive",
            "notes": note,
        })

    # Guarantee minimum of 5
    while len(triggers) < 5:
        triggers.append({
            "id": f"pos-{len(triggers) + 1}",
            "prompt": f"help me with {slug}",
            "should_trigger": True,
            "category": "positive",
            "notes": "Generic fallback request",
        })

    return triggers[:8]


def generate_negative_triggers(name: str, desc: str, content: str = "") -> list[dict]:
    """Generate 3–5 negative trigger test cases.

    Parses "do NOT use" / "NOT for" clauses from description and picks
    generic off-topic prompts from domains unrelated to the skill.
    """
    slug = _slugify(name)
    triggers: list[dict] = []

    # Extract "do NOT use for X" / "NOT for X" patterns from description
    not_for_re = re.compile(
        r"(?:do NOT use|NOT for|not for)\s+(?:for\s+)?([^.;,\n]{5,60})",
        re.IGNORECASE,
    )
    for m in not_for_re.finditer(desc):
        clause = m.group(1).strip().rstrip(".,;")
        prompt = f"Can you help me {clause.lower()}?"
        triggers.append({
            "id": f"neg-{len(triggers) + 1}",
            "prompt": prompt,
            "should_trigger": False,
            "category": "negative",
            "notes": f"Extracted from 'NOT for' clause: \"{clause}\"",
        })

    # Pick generic negatives that are clearly outside the skill's domain
    purpose = _extract_skill_purpose(desc, content)
    domain_lower = " ".join(purpose["domain_terms"]).lower()

    # Pool of off-topic prompts across many domains
    negative_pool = [
        ("Can you review this Python function for bugs?", "code review"),
        ("Help me set up CI/CD for my repository", "ci/cd"),
        ("Write me a unit test for this class", "testing"),
        ("Refactor this module to use dependency injection", "refactoring"),
        ("Debug why my API returns a 500 error", "debugging"),
        ("Help me write a README for this project", "documentation"),
        ("Set up pre-commit hooks with eslint and prettier", "linting"),
        ("Deploy my application to production", "deployment"),
        ("Optimize this SQL query for performance", "database"),
        ("Help me design the authentication flow", "authentication"),
        ("Create a Docker container for this service", "container"),
        ("Translate this error message to German", "translation"),
    ]

    # Filter out prompts that overlap with the skill's domain
    for text, domain in negative_pool:
        if len(triggers) >= 5:
            break
        # Skip if this domain overlaps with the skill's domain
        if domain in domain_lower or any(d in text.lower() for d in purpose["domain_terms"][:5]):
            continue
        triggers.append({
            "id": f"neg-{len(triggers) + 1}",
            "prompt": text,
            "should_trigger": False,
            "category": "negative",
            "notes": f"Off-topic ({domain}) — outside skill domain",
        })

    # Guarantee minimum of 3
    extra_generics = [
        "What is the weather like today?",
        "Tell me a joke about programming",
        "How do I make pasta carbonara?",
    ]
    i = 0
    while len(triggers) < 3 and i < len(extra_generics):
        triggers.append({
            "id": f"neg-{len(triggers) + 1}",
            "prompt": extra_generics[i],
            "should_trigger": False,
            "category": "negative",
            "notes": "Clearly off-topic — unrelated domain",
        })
        i += 1

    return triggers[:5]


def generate_edge_triggers(name: str, desc: str = "") -> list[dict]:
    """Generate 2–3 edge trigger test cases covering ambiguous scenarios."""
    slug = _slugify(name)
    edges = [
        {
            "id": "edge-1",
            "prompt": f"something about {slug}",
            "should_trigger": True,
            "category": "edge",
            "notes": "Minimal — vague reference to skill name; should trigger and ask for details",
        },
        {
            "id": "edge-2",
            "prompt": f"help me with this",
            "should_trigger": False,
            "category": "edge",
            "notes": "Too vague — no skill name or domain terms; should NOT trigger",
        },
    ]

    # If description has domain terms, add an ambiguous domain-adjacent prompt
    purpose = _extract_skill_purpose(desc, "")
    if purpose["domain_terms"]:
        term = purpose["domain_terms"][0]
        edges.append({
            "id": "edge-3",
            "prompt": f"I have a question about {term}",
            "should_trigger": False,
            "category": "edge",
            "notes": f"Domain-adjacent ('{term}') but not an actionable request",
        })

    return edges


# ---------------------------------------------------------------------------
# Test case and edge case generation
# ---------------------------------------------------------------------------

def generate_test_cases(name: str, desc: str = "") -> list[dict]:
    """Generate 2–3 functional test cases with inline assertions.

    Uses the skill description to generate domain-appropriate test prompts.
    """
    slug = _slugify(name)
    purpose = _extract_skill_purpose(desc, "")

    # Build a representative prompt from the skill's domain
    if purpose["use_when"]:
        domain_prompt = purpose["use_when"][0]
    elif purpose["actions"]:
        domain_prompt = f"Can you {purpose['actions'][0].lower()}?"
    else:
        domain_prompt = f"Help me with {slug}"

    return [
        {
            "id": "tc-1",
            "prompt": domain_prompt,
            "input_files": [],
            "assertions": [
                {
                    "type": "excludes",
                    "value": "TODO",
                    "description": "No placeholder text in output",
                },
                {
                    "type": "pattern",
                    "value": "\\w{4,}",
                    "description": "Produces meaningful output (not empty)",
                },
            ],
        },
        {
            "id": "tc-2",
            "prompt": f"I need help with {slug}",
            "input_files": [],
            "assertions": [
                {
                    "type": "pattern",
                    "value": "\\w{4,}",
                    "description": "Produces meaningful output",
                },
            ],
        },
        {
            "id": "tc-3",
            "prompt": f"help",
            "input_files": [],
            "assertions": [
                {
                    "type": "pattern",
                    "value": "\\?|which|what|specify|provide",
                    "description": "Asks for clarification when prompt is too vague",
                },
            ],
        },
    ]


def generate_edge_cases(name: str) -> list[dict]:
    """Generate 2 structural edge-case entries."""
    return [
        {
            "id": "ec-1",
            "prompt": "Improve my skill",
            "category": "minimal_input",
            "expected_behavior": "Ask for the skill path before proceeding",
            "assertions": [
                {
                    "type": "pattern",
                    "value": "\\?|path|which",
                    "description": "Asks for clarification about which skill",
                }
            ],
        },
        {
            "id": "ec-2",
            "prompt": f"/nonexistent/SKILL.md",
            "category": "invalid_path",
            "expected_behavior": "Report that the file was not found gracefully",
            "assertions": [
                {
                    "type": "pattern",
                    "value": "(?i)(not found|doesn't exist|cannot find|no such)",
                    "description": "Reports missing file gracefully",
                }
            ],
        },
    ]


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------

def build_eval_suite(skill_path: str) -> dict:
    """Orchestrate all generation steps and return the complete eval-suite dict.

    Steps:
      1. Read file with size guard
      2. Parse frontmatter
      3. Extract trigger phrases
      4. Generate triggers, test cases, edge cases
      5. Return dict matching eval-suite-template.json schema
    """
    p = Path(skill_path).resolve()
    if not p.exists():
        print(f"Error: skill file not found: {skill_path}", file=sys.stderr)
        sys.exit(1)

    if p.stat().st_size > MAX_SKILL_SIZE:
        print(
            f"Error: skill file exceeds {MAX_SKILL_SIZE} bytes ({p.stat().st_size} bytes)",
            file=sys.stderr,
        )
        sys.exit(1)

    content = p.read_text(encoding="utf-8")

    fm = parse_frontmatter(content)
    name = fm["name"] or p.parent.name or "unknown-skill"
    desc = fm["description"] or ""

    phrases = extract_trigger_phrases(content)

    positive = generate_positive_triggers(name, desc, phrases, content)
    negative = generate_negative_triggers(name, desc, content)
    edge = generate_edge_triggers(name, desc)
    test_cases = generate_test_cases(name, desc)
    edge_cases = generate_edge_cases(name)

    return {
        "skill_name": name,
        "version": "1.0.0",
        "created_by": "init-skill",
        "triggers": positive + negative + edge,
        "test_cases": test_cases,
        "edge_cases": edge_cases,
    }


# ---------------------------------------------------------------------------
# Baseline scoring
# ---------------------------------------------------------------------------

def run_baseline(skill_path: str, eval_suite_path: str) -> dict:
    """Run score-skill.py and return parsed results.

    Returns {"composite": float, "dimensions": dict}.
    On failure returns {"composite": 0, "dimensions": {}, "error": str}.
    """
    scorer = SCRIPT_DIR / "score-skill.py"
    if not scorer.exists():
        return {
            "composite": 0,
            "dimensions": {},
            "error": f"scorer not found: {scorer}",
        }

    cmd = [
        sys.executable,
        str(scorer),
        skill_path,
        "--eval-suite",
        eval_suite_path,
        "--json",
    ]

    print("Computing baseline score...", end="", file=sys.stderr, flush=True)
    _t0 = time.monotonic()

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        elapsed = time.monotonic() - _t0
        print(f"  timeout [{elapsed:.1f}s]", file=sys.stderr)
        return {"composite": 0, "dimensions": {}, "error": "scorer timed out after 60s (eval suite may be too large)"}
    except Exception as exc:
        elapsed = time.monotonic() - _t0
        print(f"  error [{elapsed:.1f}s]", file=sys.stderr)
        return {"composite": 0, "dimensions": {}, "error": str(exc)}

    elapsed = time.monotonic() - _t0
    print(f"  done [{elapsed:.1f}s]", file=sys.stderr)

    if result.returncode != 0:
        err_msg = result.stderr.strip()[:200] or result.stdout.strip()[:200]
        return {"composite": 0, "dimensions": {}, "error": err_msg}

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        return {"composite": 0, "dimensions": {}, "error": f"JSON parse error: {exc}"}

    composite = float(data.get("composite_score", 0))
    dimensions = {k: v for k, v in data.get("dimensions", {}).items()}
    return {"composite": composite, "dimensions": dimensions}


# ---------------------------------------------------------------------------
# Summary helpers
# ---------------------------------------------------------------------------

def _count_assertions(suite: dict) -> int:
    total = 0
    for tc in suite.get("test_cases", []):
        total += len(tc.get("assertions", []))
    for ec in suite.get("edge_cases", []):
        total += len(ec.get("assertions", []))
    return total


def _trigger_counts(suite: dict) -> dict:
    pos = sum(1 for t in suite["triggers"] if t["category"] == "positive")
    neg = sum(1 for t in suite["triggers"] if t["category"] == "negative")
    edg = sum(1 for t in suite["triggers"] if t["category"] == "edge")
    return {"positive": pos, "negative": neg, "edge": edg}


def _tc_assertions(suite: dict) -> int:
    return sum(len(tc.get("assertions", [])) for tc in suite.get("test_cases", []))


def _ec_assertions(suite: dict) -> int:
    return sum(len(ec.get("assertions", [])) for ec in suite.get("edge_cases", []))


def print_human_summary(
    suite: dict,
    skill_path: str,
    eval_suite_path: str,
    baseline: dict,
    dry_run: bool,
) -> None:
    name = suite["skill_name"]
    tc = _trigger_counts(suite)
    total_triggers = tc["positive"] + tc["negative"] + tc["edge"]
    num_tc = len(suite.get("test_cases", []))
    num_ec = len(suite.get("edge_cases", []))
    assertions_tc = _tc_assertions(suite)
    assertions_ec = _ec_assertions(suite)

    print(f"Schliff Init: {name}")
    print("=" * max(len(name) + 16, 32))
    print()
    print("Generated eval-suite.json:")
    print(
        f"  Triggers:    {tc['positive']} positive + {tc['negative']} negative"
        f" + {tc['edge']} edge = {total_triggers} total"
    )
    print(f"  Test cases:  {num_tc} ({assertions_tc} assertions)")
    print(f"  Edge cases:  {num_ec} ({assertions_ec} assertions)")
    print()

    if baseline.get("error"):
        print(f"Baseline Score: unavailable ({baseline['error']})")
    else:
        score = baseline['composite']
        grade = score_to_grade(score)
        grade_str = grade_colored(grade)
        print(f"Baseline Score: {score:.0f}/100  {grade_str}")
        print()
        dims = baseline.get("dimensions", {})
        if dims:
            for dim, s in dims.items():
                if isinstance(s, (int, float)) and s >= 0:
                    bar = colored_bar(s)
                    print(f"  {dim:15s} {bar}  {s:.0f}/100")
                else:
                    print(f"  {dim:15s} {'n/a':>15s}")

    print()
    if dry_run:
        print("(dry-run: eval-suite.json was NOT written)")
    else:
        print(f"Written: {eval_suite_path}")

    print()
    # Contextual next steps based on score
    if not baseline.get("error"):
        score = baseline['composite']
        if score >= 80:
            print("Strong baseline! Run /schliff:auto for final polish.")
        elif score >= 60:
            # Find weakest dimension
            dims = baseline.get("dimensions", {})
            scored = {d: s for d, s in dims.items() if isinstance(s, (int, float)) and s >= 0}
            if scored:
                weakest = min(scored, key=lambda d: scored[d])
                print(f"Good start. Focus on {weakest}. Run /schliff:auto to improve.")
            else:
                print("Good start. Run /schliff:auto to start improving.")
        else:
            print("Room to grow! Run /schliff to set a specific GOAL.")
    else:
        print("Next: Run /schliff:auto to start autonomous improvement.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Schliff eval-suite bootstrapper — generate eval-suite.json from SKILL.md",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("skill_path", nargs="?", default=None, help="Path to SKILL.md (auto-discovered if omitted)")
    parser.add_argument(
        "--json",
        action="store_true",
        dest="output_json",
        help="Output machine-readable JSON summary",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate but do not write eval-suite.json",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output path for eval-suite.json (default: same directory as SKILL.md)",
    )

    args = parser.parse_args()

    # Auto-discovery: find SKILL.md if no path given
    if args.skill_path is None:
        candidates = [Path("./SKILL.md")]
        # Search parent dirs up to depth 2
        for p in Path(".").glob("**/SKILL.md"):
            if p not in candidates and len(p.parts) <= 4:
                candidates.append(p)
        found = None
        for c in candidates:
            if c.exists():
                found = c
                break
        if found is None:
            print("Error: no SKILL.md found. Provide a path or run from a skill directory.", file=sys.stderr)
            sys.exit(1)
        print(f"Found SKILL.md at {found}", file=sys.stderr)
        args.skill_path = str(found)

    skill_path = str(Path(args.skill_path).resolve())

    suite = build_eval_suite(skill_path)

    # Determine output path
    if args.output:
        eval_suite_path = str(Path(args.output).resolve())
    else:
        skill_dir = Path(skill_path).parent
        eval_suite_path = str(skill_dir / "eval-suite.json")

    # Write unless dry-run
    if not args.dry_run:
        try:
            Path(eval_suite_path).write_text(
                json.dumps(suite, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError as exc:
            print(f"Error: could not write eval-suite.json: {exc}", file=sys.stderr)
            sys.exit(1)

    # Run baseline (always, even on dry-run, so the user gets a score)
    baseline = run_baseline(skill_path, eval_suite_path)

    # Output
    tc = _trigger_counts(suite)
    total_triggers = tc["positive"] + tc["negative"] + tc["edge"]
    assertions_total = _count_assertions(suite)

    if args.output_json:
        summary = {
            "skill_name": suite["skill_name"],
            "skill_path": skill_path,
            "eval_suite_path": eval_suite_path,
            "triggers": tc,
            "test_cases": len(suite.get("test_cases", [])),
            "edge_cases": len(suite.get("edge_cases", [])),
            "assertions_total": assertions_total,
            "baseline": baseline,
            "dry_run": args.dry_run,
        }
        print(json.dumps(summary, indent=2))
    else:
        print_human_summary(
            suite=suite,
            skill_path=skill_path,
            eval_suite_path=eval_suite_path,
            baseline=baseline,
            dry_run=args.dry_run,
        )


if __name__ == "__main__":
    main()
