#!/usr/bin/env python3
"""Schliff Sync — Cross-file instruction analysis.

Discovers all instruction files in a repository and extracts
actionable directives for consistency analysis.
"""
from __future__ import annotations

import os
import re
import sys
from difflib import SequenceMatcher
from typing import Dict, List, Tuple

# Import from shared (same directory)
from shared import read_skill_safe, strip_frontmatter

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Directories to skip during discovery (common non-source dirs)
_EXCLUDED_DIRS: frozenset[str] = frozenset({
    ".git", "node_modules", "venv", ".venv",
    "__pycache__", ".tox", "dist", "build", ".eggs",
})

# Basename → format mapping (all comparisons are case-insensitive)
_INSTRUCTION_FILES: dict[str, str] = {
    "skill.md": "skill.md",
    "claude.md": "claude.md",
    ".cursorrules": "cursorrules",
    "agents.md": "agents.md",
}

# ---------------------------------------------------------------------------
# Directive extraction patterns — bounded, no nested quantifiers
# ---------------------------------------------------------------------------

# Strip fenced code blocks to avoid matching examples as directives.
# Non-greedy .*? is safe (no nested quantifiers) and handles inline
# backticks within code blocks (e.g., `variable` references).
_RE_CODE_BLOCK = re.compile(r"```.*?```", re.DOTALL)

# Sentence splitting: split on sentence-ending punctuation followed by
# whitespace or newline.  Keeps the split simple and bounded.
_RE_SENTENCE_SPLIT = re.compile(r"(?<=\.)\s+|(?<=\.)\n|(?<=!)\n|(?<=\?)\n")

# Imperative patterns — each group:
#   group(1) = keyword, group(2) = verb, group(3) = rest (object)
# "Always/Must + verb + object"
_RE_ALWAYS_MUST = re.compile(
    r"\b(always|must)\s+(?!not\b)([a-z]\w*)\s+(.+)",
    re.IGNORECASE,
)
# "Never/Must not/Do not/Don't + verb + object"
_RE_NEVER_DONOT = re.compile(
    r"\b(never|must\s+not|do\s+not|don't)\s+([a-z]\w*)\s+(.+)",
    re.IGNORECASE,
)
# "Prefer/Favor/Default to + object"
_RE_PREFERENCE = re.compile(
    r"\b(prefer|favor|default\s+to)\s+(.+)",
    re.IGNORECASE,
)
# "Avoid/Discourage + object"
_RE_AVOIDANCE = re.compile(
    r"\b(avoid|discourage)\s+(.+)",
    re.IGNORECASE,
)
# "Use/Require + object"
_RE_USE_REQUIRE = re.compile(
    r"\b(use|require)\s+(.+)",
    re.IGNORECASE,
)

# Config value patterns: key = value, key: value, key=value
# Key must be snake_case or kebab-case identifier (3-40 chars)
_RE_CONFIG = re.compile(
    r"^[ \t]*([a-z][a-z0-9_-]{2,39})\s*[:=]\s*(.+)$",
    re.MULTILINE,
)

# Validate that a key looks like a config name (not prose)
_RE_CONFIG_KEY = re.compile(r"^[a-z][a-z0-9]*(?:[_-][a-z0-9]+)+$")


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def discover_all_instruction_files(repo_root: str) -> List[Dict]:
    """Walk *repo_root* and find all instruction files.

    Returns a sorted list of dicts:
        {"path": str, "format": str, "relative_path": str}

    Directories in ``_EXCLUDED_DIRS`` are pruned in-place so
    ``os.walk`` never descends into them.
    """
    root = os.path.abspath(repo_root)
    results: list[dict] = []

    for dirpath, dirnames, filenames in os.walk(root):
        # Prune excluded directories in-place (modifying dirnames[:])
        dirnames[:] = [
            d for d in dirnames
            if d not in _EXCLUDED_DIRS
        ]

        for fname in filenames:
            key = fname.lower()
            fmt = _INSTRUCTION_FILES.get(key)
            if fmt is not None:
                full = os.path.join(dirpath, fname)
                rel = os.path.relpath(full, root)
                results.append({
                    "path": full,
                    "format": fmt,
                    "relative_path": rel,
                })

    results.sort(key=lambda r: r["relative_path"])
    return results


# ---------------------------------------------------------------------------
# Directive extraction
# ---------------------------------------------------------------------------

def _char_offset_to_line(content: str, offset: int) -> int:
    """Convert a character offset to an approximate 1-based line number."""
    return content[:offset].count("\n") + 1


def _clean_object(text: str) -> str:
    """Trim trailing punctuation and whitespace from an extracted object."""
    return text.strip().rstrip(".,;:!?").strip()


def extract_directives(content: str) -> List[Dict]:
    """Extract actionable directives from instruction file *content*.

    Returns a list of dicts with at minimum:
        {"text": str, "verb": str, "object": str,
         "polarity": str, "line": int}

    Config directives additionally carry ``config_key`` and ``config_value``.

    The function matches clear imperative patterns and config assignments.
    Higher-priority patterns (always/must/never) are checked first; the
    lower-priority ``use``/``require`` pattern may match common prose.
    """
    # Work on a copy with frontmatter removed for pattern matching,
    # but keep original to compute line numbers.
    original = content
    stripped = strip_frontmatter(content)

    # Determine the character offset where stripped content starts in
    # the original so line numbers stay accurate.
    fm_offset = len(original) - len(stripped) if stripped != original else 0

    # Remove fenced code blocks so examples are not treated as directives
    cleaned = _RE_CODE_BLOCK.sub("", stripped)

    directives: list[dict] = []

    # --- Imperative directives (sentence-level) ---
    sentences = _RE_SENTENCE_SPLIT.split(cleaned)
    # Track character position in *cleaned* for line number estimation
    pos = 0
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            pos += 1
            continue

        # Find the sentence's position in the stripped content for line calc
        sent_offset = stripped.find(sentence, max(0, pos - 20))
        if sent_offset == -1:
            sent_offset = pos
        line = _char_offset_to_line(original, sent_offset + fm_offset)

        matched = False

        # Always / Must
        m = _RE_ALWAYS_MUST.search(sentence)
        if m and not matched:
            directives.append({
                "text": sentence,
                "verb": m.group(2).lower(),
                "object": _clean_object(m.group(3)),
                "polarity": "positive",
                "line": line,
            })
            matched = True

        # Never / Must not / Do not / Don't
        m = _RE_NEVER_DONOT.search(sentence)
        if m and not matched:
            directives.append({
                "text": sentence,
                "verb": m.group(2).lower(),
                "object": _clean_object(m.group(3)),
                "polarity": "negative",
                "line": line,
            })
            matched = True

        # Prefer / Favor / Default to
        m = _RE_PREFERENCE.search(sentence)
        if m and not matched:
            directives.append({
                "text": sentence,
                "verb": m.group(1).lower(),
                "object": _clean_object(m.group(2)),
                "polarity": "preference",
                "line": line,
            })
            matched = True

        # Avoid / Discourage
        m = _RE_AVOIDANCE.search(sentence)
        if m and not matched:
            directives.append({
                "text": sentence,
                "verb": m.group(1).lower(),
                "object": _clean_object(m.group(2)),
                "polarity": "avoidance",
                "line": line,
            })
            matched = True

        # Use / Require
        m = _RE_USE_REQUIRE.search(sentence)
        if m and not matched:
            directives.append({
                "text": sentence,
                "verb": m.group(1).lower(),
                "object": _clean_object(m.group(2)),
                "polarity": "positive",
                "line": line,
            })
            matched = True

        pos = sent_offset + len(sentence)

    # --- Config directives (line-level on cleaned content) ---
    for m in _RE_CONFIG.finditer(cleaned):
        key = m.group(1)
        value = m.group(2).strip()
        # Strip trailing inline comments (e.g. "120  # python" → "120")
        value = re.sub(r"\s*#.*$", "", value).strip()
        # Only accept keys that look like actual config names
        if not _RE_CONFIG_KEY.match(key):
            continue
        # Skip if value is empty or looks like prose (more than 5 words)
        if not value or len(value.split()) > 5:
            continue
        sent_offset = stripped.find(m.group(0).strip())
        if sent_offset == -1:
            sent_offset = m.start()
        line = _char_offset_to_line(original, sent_offset + fm_offset)
        directives.append({
            "text": m.group(0).strip(),
            "verb": "set",
            "object": f"{key} = {value}",
            "polarity": "config",
            "config_key": key,
            "config_value": value,
            "line": line,
        })

    return directives


# ---------------------------------------------------------------------------
# Combined loader
# ---------------------------------------------------------------------------

def load_all_directives(repo_root: str) -> List[Dict]:
    """Discover all instruction files and extract their directives.

    Returns a flat list of dicts:
        {"file": str, "format": str, "directive": dict}

    Files that cannot be read (permissions, encoding, size) are
    silently skipped to keep the process robust.
    """
    results: list[dict] = []

    for entry in discover_all_instruction_files(repo_root):
        try:
            content = read_skill_safe(entry["path"])
        except (FileNotFoundError, ValueError, OSError) as exc:
            print(f"Warning: skipping {entry['path']}: {exc}", file=sys.stderr)
            continue

        for directive in extract_directives(content):
            results.append({
                "file": entry["relative_path"],
                "format": entry["format"],
                "directive": directive,
            })

    return results


def group_directives_by_file(flat: List[Dict]) -> List[Dict]:
    """Reshape ``load_all_directives`` output for analysis functions.

    Converts the flat list of ``{"file", "format", "directive"}`` entries
    into a grouped list of ``{"path", "format", "directives"}`` per file,
    which is the format expected by :func:`find_contradictions`,
    :func:`find_gaps`, and :func:`find_redundancies`.
    """
    grouped: Dict[str, Dict] = {}
    for entry in flat:
        key = entry["file"]
        if key not in grouped:
            grouped[key] = {
                "path": entry["file"],
                "format": entry["format"],
                "directives": [],
            }
        grouped[key]["directives"].append(entry["directive"])
    return list(grouped.values())


# ---------------------------------------------------------------------------
# Analysis constants
# ---------------------------------------------------------------------------

OPPOSITIONS: List[Tuple[frozenset, frozenset]] = [
    (frozenset({"tabs", "tab-based", "use tabs"}),
     frozenset({"spaces", "space-based", "use spaces"})),
    (frozenset({"single quotes", "single-quote"}),
     frozenset({"double quotes", "double-quote"})),
    (frozenset({"camelcase", "camel case"}),
     frozenset({"snake_case", "snake case"})),
    (frozenset({"tdd", "test-driven", "test first"}),
     frozenset({"skip tests", "no tests", "tests optional"})),
    (frozenset({"verbose", "detailed logging"}),
     frozenset({"concise", "minimal logging"})),
    (frozenset({"strict mode", "strict"}),
     frozenset({"loose", "permissive"})),
    (frozenset({"semicolons", "always semicolons"}),
     frozenset({"no semicolons", "omit semicolons"})),
]

TOPIC_KEYWORDS: Dict[str, List[str]] = {
    "build": ["build", "compile", "bundle", "webpack", "vite", "turbopack"],
    "test": ["test", "jest", "pytest", "vitest", "coverage", "spec"],
    "style": ["lint", "format", "prettier", "eslint", "style", "indent"],
    "security": ["secret", "token", "credential", "api key", "permission", "auth"],
    "git": ["commit", "branch", "merge", "rebase", "push", "pull request"],
    "deploy": ["deploy", "ci/cd", "pipeline", "staging", "production"],
}

_ARTICLES = frozenset({"the", "a", "an", "this", "that", "any", "all"})


# ---------------------------------------------------------------------------
# Analysis helpers
# ---------------------------------------------------------------------------

def _normalize(text: str) -> str:
    """Lowercase, strip extra whitespace, remove articles."""
    words = text.lower().split()
    words = [w for w in words if w not in _ARTICLES]
    return " ".join(words)


def _normalize_key(verb: str, obj: str) -> Tuple[str, str]:
    """Normalize a (verb, object) pair for comparison."""
    return (verb.lower().strip(), _normalize(obj))


def _file_mentions_any(file_dict: dict, terms: frozenset) -> List[dict]:
    """Return directives whose normalized text contains any term."""
    hits = []
    for d in file_dict.get("directives", []):
        text_lower = d["text"].lower()
        for term in terms:
            if term in text_lower:
                hits.append(d)
                break
    return hits


# ---------------------------------------------------------------------------
# Contradiction detection
# ---------------------------------------------------------------------------

def find_contradictions(files: List[dict]) -> List[dict]:
    """Detect polarity, config, and semantic contradictions across files.

    Only cross-file contradictions are detected; intra-file conflicts
    are not reported (see ``scoring/clarity.py`` for single-file analysis).

    Each file dict has:
        {"path": str, "format": str, "directives": list[dict]}

    Returns list of contradiction dicts with type, file paths, directive
    texts, and severity.
    """
    results: List[dict] = []
    for i, file_a in enumerate(files):
        for file_b in files[i + 1:]:
            _find_polarity_conflicts(file_a, file_b, results)
            _find_config_conflicts(file_a, file_b, results)
            _find_semantic_oppositions(file_a, file_b, results)
    return results


def _find_polarity_conflicts(
    file_a: dict, file_b: dict, results: List[dict]
) -> None:
    """Detect positive/negative polarity conflicts on same (verb, object)."""
    positive_a: Dict[Tuple[str, str], dict] = {}
    negative_a: Dict[Tuple[str, str], dict] = {}

    for d in file_a.get("directives", []):
        key = _normalize_key(d.get("verb", ""), d.get("object", ""))
        if not key[0]:
            continue
        if d.get("polarity") == "positive":
            positive_a[key] = d
        elif d.get("polarity") == "negative":
            negative_a[key] = d

    for d in file_b.get("directives", []):
        key = _normalize_key(d.get("verb", ""), d.get("object", ""))
        if not key[0]:
            continue
        polarity = d.get("polarity", "")
        if polarity == "negative" and key in positive_a:
            results.append({
                "type": "polarity",
                "file_a": file_a["path"],
                "file_b": file_b["path"],
                "directive_a": positive_a[key]["text"],
                "directive_b": d["text"],
                "severity": "high",
            })
        elif polarity == "positive" and key in negative_a:
            results.append({
                "type": "polarity",
                "file_a": file_a["path"],
                "file_b": file_b["path"],
                "directive_a": negative_a[key]["text"],
                "directive_b": d["text"],
                "severity": "high",
            })


def _find_config_conflicts(
    file_a: dict, file_b: dict, results: List[dict]
) -> None:
    """Detect config directives with same key but different values."""
    configs_a: Dict[str, dict] = {}
    for d in file_a.get("directives", []):
        if d.get("polarity") == "config" and d.get("config_key"):
            configs_a[d["config_key"].lower().strip()] = d

    for d in file_b.get("directives", []):
        if d.get("polarity") != "config" or not d.get("config_key"):
            continue
        key = d["config_key"].lower().strip()
        if key in configs_a:
            val_a = str(configs_a[key].get("config_value", "")).strip()
            val_b = str(d.get("config_value", "")).strip()
            if val_a != val_b:
                results.append({
                    "type": "config",
                    "file_a": file_a["path"],
                    "file_b": file_b["path"],
                    "directive_a": configs_a[key]["text"],
                    "directive_b": d["text"],
                    "severity": "high",
                })


def _find_semantic_oppositions(
    file_a: dict, file_b: dict, results: List[dict]
) -> None:
    """Detect semantic oppositions using the OPPOSITIONS table."""
    for set1, set2 in OPPOSITIONS:
        hits_a_1 = _file_mentions_any(file_a, set1)
        hits_b_2 = _file_mentions_any(file_b, set2)
        if hits_a_1 and hits_b_2:
            results.append({
                "type": "semantic",
                "file_a": file_a["path"],
                "file_b": file_b["path"],
                "directive_a": hits_a_1[0]["text"],
                "directive_b": hits_b_2[0]["text"],
                "severity": "medium",
            })
        hits_a_2 = _file_mentions_any(file_a, set2)
        hits_b_1 = _file_mentions_any(file_b, set1)
        if hits_a_2 and hits_b_1:
            results.append({
                "type": "semantic",
                "file_a": file_a["path"],
                "file_b": file_b["path"],
                "directive_a": hits_a_2[0]["text"],
                "directive_b": hits_b_1[0]["text"],
                "severity": "medium",
            })


# ---------------------------------------------------------------------------
# Gap detection
# ---------------------------------------------------------------------------

def find_gaps(files: List[dict]) -> List[dict]:
    """Find topics covered in some files but missing from others."""
    if len(files) < 2:
        return []

    results: List[dict] = []
    for topic, keywords in TOPIC_KEYWORDS.items():
        present_in: List[str] = []
        missing_from: List[str] = []
        for f in files:
            texts_lower = " ".join(
                d["text"].lower() for d in f.get("directives", [])
            )
            if any(kw in texts_lower for kw in keywords):
                present_in.append(f["path"])
            else:
                missing_from.append(f["path"])
        if present_in and missing_from:
            results.append({
                "topic": topic,
                "present_in": present_in,
                "missing_from": missing_from,
            })
    return results


# ---------------------------------------------------------------------------
# Redundancy detection
# ---------------------------------------------------------------------------

_MAX_REDUNDANCY_DIRECTIVES = 150  # cap to avoid O(n²) blowup on large repos


def find_redundancies(files: List[dict]) -> List[dict]:
    """Find near-duplicate directives across different files (similarity > 0.80).

    Intra-file duplicates are ignored.  Comparison is O(n²) on the total
    number of directives; capped at _MAX_REDUNDANCY_DIRECTIVES to keep
    runtime under ~1s on typical hardware.
    """
    all_directives: List[Tuple[str, str, str]] = []
    for f in files:
        for d in f.get("directives", []):
            norm = _normalize(d["text"])
            if norm:
                all_directives.append((norm, d["text"], f["path"]))

    if len(all_directives) > _MAX_REDUNDANCY_DIRECTIVES:
        # Truncate to cap; prefer directives from more files for coverage
        all_directives = all_directives[:_MAX_REDUNDANCY_DIRECTIVES]

    n = len(all_directives)
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x: int, y: int) -> None:
        px, py = find(x), find(y)
        if px != py:
            parent[px] = py

    best_sim: Dict[int, float] = {}

    for i in range(n):
        for j in range(i + 1, n):
            if all_directives[i][2] == all_directives[j][2]:
                continue
            ratio = SequenceMatcher(
                None, all_directives[i][0], all_directives[j][0]
            ).ratio()
            if ratio > 0.80:
                union(i, j)
                root = find(i)
                best_sim[root] = max(best_sim.get(root, 0.0), ratio)

    groups: Dict[int, List[int]] = {}
    for i in range(n):
        root = find(i)
        if root in best_sim:
            groups.setdefault(root, []).append(i)

    results: List[dict] = []
    seen_roots: set = set()
    for root, members in groups.items():
        if root in seen_roots:
            continue
        seen_roots.add(root)
        paths = list(dict.fromkeys(all_directives[m][2] for m in members))
        if len(paths) < 2:
            continue
        results.append({
            "directive": all_directives[members[0]][1],
            "found_in": paths,
            "similarity": round(best_sim.get(root, 0.0), 2),
        })
    return results


# ---------------------------------------------------------------------------
# Consistency score
# ---------------------------------------------------------------------------

def compute_consistency_score(
    contradictions: List[dict],
    gaps: List[dict],
    redundancies: List[dict],
) -> int:
    """Compute overall consistency score (0-100).

    Penalties are weighted by severity:
    - Contradictions: high=-15, medium=-7 (polarity vs semantic opposition)
    - Gaps: -5 per missing topic
    - Redundancies: -3 per duplicate cluster
    """
    contradiction_penalty = sum(
        15 if c.get("severity") == "high" else 7
        for c in contradictions
    )
    score = 100 - contradiction_penalty - len(gaps) * 5 - len(redundancies) * 3
    return max(0, min(100, score))


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------

def _short(text: str, maxlen: int = 60) -> str:
    """Truncate text for display."""
    text = text.strip().replace("\n", " ")
    if len(text) > maxlen:
        return text[:maxlen - 3] + "..."
    return text


def _basename(path: str) -> str:
    """Extract filename from path."""
    return os.path.basename(path)


def format_sync_report(
    contradictions: List[dict],
    gaps: List[dict],
    redundancies: List[dict],
    score: int,
    files: List[dict],
) -> str:
    """Format a colored sync report for terminal output."""
    R = "\033[31m"   # red
    Y = "\033[33m"   # yellow
    G = "\033[32m"   # green
    C = "\033[36m"   # cyan
    B = "\033[1m"    # bold
    D = "\033[2m"    # dim
    N = "\033[0m"    # reset

    lines: list[str] = []

    lines.append("")
    lines.append(f"{B}═══ Schliff Sync Report ═══{N}")
    lines.append("")

    lines.append(f"Files analyzed: {B}{len(files)}{N}")
    for f in files:
        path = f.get("path", "unknown")
        fmt = f.get("format", "unknown")
        lines.append(f"  {D}{path}{N} ({C}{fmt}{N})")
    lines.append("")

    if score >= 80:
        sc = f"{G}{B}{score}/100{N}"
    elif score >= 50:
        sc = f"{Y}{B}{score}/100{N}"
    else:
        sc = f"{R}{B}{score}/100{N}"
    lines.append(f"Consistency Score: {sc}")
    lines.append("")

    lines.append(f"─── Contradictions ({len(contradictions)}) ───")
    if contradictions:
        for c in contradictions:
            sev = c["severity"].upper()
            sev_c = R if sev == "HIGH" else Y
            if c["type"] == "semantic":
                lines.append(
                    f"  {sev_c}⚠ {sev}{N}: Semantic: "
                    f"{_short(c['directive_a'])} vs {_short(c['directive_b'])} "
                    f"across {_basename(c['file_a'])} and {_basename(c['file_b'])}"
                )
            else:
                lines.append(
                    f"  {sev_c}⚠ {sev}{N}: "
                    f"\"{_short(c['directive_a'])}\" ({_basename(c['file_a'])}) "
                    f"vs \"{_short(c['directive_b'])}\" ({_basename(c['file_b'])})"
                )
    else:
        lines.append(f"  {G}None detected.{N}")
    lines.append("")

    lines.append(f"─── Gaps ({len(gaps)}) ───")
    if gaps:
        for g in gaps:
            present = ", ".join(_basename(p) for p in g["present_in"])
            missing = ", ".join(_basename(p) for p in g["missing_from"])
            lines.append(
                f"  {C}ℹ{N} Topic '{g['topic']}' covered in {present} "
                f"but missing from {missing}"
            )
    else:
        lines.append(f"  {G}None detected.{N}")
    lines.append("")

    lines.append(f"─── Redundancies ({len(redundancies)}) ───")
    if redundancies:
        for r in redundancies:
            found = " and ".join(_basename(p) for p in r["found_in"])
            pct = int(r["similarity"] * 100)
            lines.append(
                f"  {Y}↔{N} \"{_short(r['directive'])}\" "
                f"found in {found} ({pct}% similar)"
            )
    else:
        lines.append(f"  {G}None detected.{N}")
    lines.append("")

    return "\n".join(lines)
