#!/usr/bin/env python3
"""SkillForge — Eval-Suite Bootstrapper

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
sys.path.insert(0, str(SCRIPT_DIR))

# Import terminal_art for grade system and score cards
try:
    from terminal_art import score_to_grade, grade_colored, colored_bar, _is_color_tty
except ImportError:
    def score_to_grade(s: float) -> str:
        for t, g in [(95,"S"),(85,"A"),(75,"B"),(65,"C"),(50,"D")]:
            if s >= t: return g
        return "F"
    def grade_colored(g: str) -> str:
        return f"[{g}]"
    def colored_bar(s: float, bar_w: int = 10) -> str:
        filled = min(bar_w, int(round(s / 100 * bar_w)))
        return "\u2588" * filled + "\u2591" * (bar_w - filled)
    def _is_color_tty() -> bool:
        return False

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
    name: str, desc: str, phrases: list[str]
) -> list[dict]:
    """Generate 5–8 positive trigger test cases.

    Templates combine extracted phrases, keyword-based prompts, generic
    fallbacks, and a skill-creator handoff scenario.
    """
    slug = _slugify(name)
    triggers: list[dict] = []

    # From extracted phrases (up to 3)
    for i, phrase in enumerate(phrases[:3]):
        triggers.append({
            "id": f"pos-{len(triggers) + 1}",
            "prompt": f"Can you {phrase.lower()} for my {slug} skill?",
            "should_trigger": True,
            "category": "positive",
            "notes": f"Derived from extracted phrase: \"{phrase}\"",
        })

    # From action keywords in description
    keywords = []
    for kw in _ACTION_VERBS:
        if kw in desc.lower():
            keywords.append(kw)
    for kw in keywords[:2]:
        triggers.append({
            "id": f"pos-{len(triggers) + 1}",
            "prompt": f"{kw.capitalize()} seems off in my skill, can you {kw} it?",
            "should_trigger": True,
            "category": "positive",
            "notes": f"Keyword \"{kw}\" found in skill description",
        })

    # Generic improvement phrases
    generic_prompts = [
        (f"make my {slug} skill better", "Exact-match trigger phrase from SKILL.md"),
        (f"optimize {slug}", "Short-form optimization request"),
        (f"audit my {slug} skill", "Audit keyword with skill name"),
        (
            f"I just created {slug} with skill-creator, now grind it to production",
            "skill-creator handoff pattern",
        ),
        (
            f"my {slug} skill scores 45/100, I need it at 80+ before shipping",
            "Numeric goal with autonomous improvement request",
        ),
        (
            f"review my {slug} skill and show me what is wrong with it",
            "Analysis-only request without path",
        ),
        (
            f"harden my {slug} skill against malformed inputs and edge cases",
            "Hardening / edge-coverage focus",
        ),
        (
            f"benchmark my {slug} skill and show scores for all dimensions",
            "Benchmark subcommand request",
        ),
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
        idx = len(triggers) + 1
        triggers.append({
            "id": f"pos-{idx}",
            "prompt": f"iterate on my {slug} skill until it is production quality",
            "should_trigger": True,
            "category": "positive",
            "notes": "Generic iteration request",
        })

    return triggers[:8]


def generate_negative_triggers(name: str, desc: str) -> list[dict]:
    """Generate 3–5 negative trigger test cases.

    Parses "do NOT use" / "NOT for" clauses from description and always
    includes a set of generic off-topic prompts.
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

    # Generic negatives — always included
    for text in _GENERIC_NEGATIVES:
        if len(triggers) >= 5:
            break
        triggers.append({
            "id": f"neg-{len(triggers) + 1}",
            "prompt": text,
            "should_trigger": False,
            "category": "negative",
            "notes": "Generic off-topic prompt — wrong domain",
        })

    # Guarantee minimum of 3
    extra_generics = [
        f"Help me write a README for my {slug} project",
        f"Set up pre-commit hooks with eslint and prettier",
        f"Deploy my application to production",
    ]
    i = 0
    while len(triggers) < 3 and i < len(extra_generics):
        triggers.append({
            "id": f"neg-{len(triggers) + 1}",
            "prompt": extra_generics[i],
            "should_trigger": False,
            "category": "negative",
            "notes": "Generic fallback negative",
        })
        i += 1

    return triggers[:5]


def generate_edge_triggers(name: str) -> list[dict]:
    """Generate 2–3 edge trigger test cases covering ambiguous scenarios."""
    slug = _slugify(name)
    return [
        {
            "id": "edge-1",
            "prompt": "improve my skill",
            "should_trigger": True,
            "category": "edge",
            "notes": "Minimal — no path, no context; should trigger and ask for details",
        },
        {
            "id": "edge-2",
            "prompt": f"this SKILL.md looks weird, fix the formatting",
            "should_trigger": True,
            "category": "edge",
            "notes": "Ambiguous — could be skill improvement or just formatting cleanup",
        },
        {
            "id": "edge-3",
            "prompt": f"benchmark my {slug} script",
            "should_trigger": False,
            "category": "edge",
            "notes": "Keyword overlap ('benchmark', skill name) but targets a script, not a skill",
        },
    ]


# ---------------------------------------------------------------------------
# Test case and edge case generation
# ---------------------------------------------------------------------------

def generate_test_cases(name: str) -> list[dict]:
    """Generate 2–3 functional test cases with inline assertions."""
    slug = _slugify(name)
    return [
        {
            "id": "tc-1",
            "prompt": f"Analyze my {slug} skill and tell me what is wrong with it",
            "input_files": [],
            "assertions": [
                {
                    "type": "contains",
                    "value": "structure",
                    "description": "Report includes structure dimension",
                },
                {
                    "type": "contains",
                    "value": "trigger",
                    "description": "Report includes trigger analysis",
                },
                {
                    "type": "pattern",
                    "value": "\\d+/100",
                    "description": "Report shows a numeric score",
                },
                {
                    "type": "excludes",
                    "value": "TODO",
                    "description": "No placeholder text in output",
                },
            ],
        },
        {
            "id": "tc-2",
            "prompt": f"Run one improvement iteration on my {slug} skill — focus on trigger accuracy",
            "input_files": [],
            "assertions": [
                {
                    "type": "contains",
                    "value": "commit",
                    "description": "Makes a git commit",
                },
                {
                    "type": "pattern",
                    "value": "(keep|discard)",
                    "description": "Makes a keep/discard decision",
                },
            ],
        },
        {
            "id": "tc-3",
            "prompt": "Improve my skill",
            "input_files": [],
            "assertions": [
                {
                    "type": "pattern",
                    "value": "\\?|path|which",
                    "description": "Asks for clarification when no path is provided",
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

    positive = generate_positive_triggers(name, desc, phrases)
    negative = generate_negative_triggers(name, desc)
    edge = generate_edge_triggers(name)
    test_cases = generate_test_cases(name)
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

    print(f"SkillForge Init: {name}")
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
            print("Strong baseline! Run /skillforge:auto for final polish.")
        elif score >= 60:
            # Find weakest dimension
            dims = baseline.get("dimensions", {})
            scored = {d: s for d, s in dims.items() if isinstance(s, (int, float)) and s >= 0}
            if scored:
                weakest = min(scored, key=lambda d: scored[d])
                print(f"Good start. Focus on {weakest}. Run /skillforge:auto to improve.")
            else:
                print("Good start. Run /skillforge:auto to start improving.")
        else:
            print("Room to grow! Run /skillforge to set a specific GOAL.")
    else:
        print("Next: Run /skillforge:auto to start autonomous improvement.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="SkillForge eval-suite bootstrapper — generate eval-suite.json from SKILL.md",
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
