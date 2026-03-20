#!/usr/bin/env python3
"""SkillForge Skill Mesh — Multi-Skill Conflict Detection

Scans all installed skills, detects trigger overlap, broken handoffs,
and scope collisions. Reports mesh health score.

Usage:
    python3 skill-mesh.py [--skill-dirs DIR...] [--json] [--incremental] [--severity info|warning|critical]

Default scan dirs: ~/.claude/skills/, .claude/skills/
"""

import argparse
import hashlib
import json
import math
import os
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional

# Import scorer functions for tokenization and description extraction
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))
import importlib
scorer = importlib.import_module("score-skill")


# --- Skill Discovery ---

def discover_skills(skill_dirs: list[str]) -> list[dict]:
    """Find all SKILL.md files in given directories.

    Returns list of skill dicts with: path, name, description, content_hash, tokens.
    """
    skills = []
    seen_paths = set()

    for skill_dir in skill_dirs:
        skill_dir_path = Path(skill_dir).expanduser()
        if not skill_dir_path.is_dir():
            continue

        for skill_md in skill_dir_path.rglob("SKILL.md"):
            real_path = str(skill_md.resolve())
            if real_path in seen_paths:
                continue
            seen_paths.add(real_path)

            try:
                content = skill_md.read_text(encoding="utf-8", errors="replace")
            except (OSError, PermissionError):
                continue

            # Skip files > 1MB
            if len(content) > 1_000_000:
                continue

            # Extract metadata
            name = "unknown"
            name_match = re.search(r"^name:\s*(.+?)$", content, re.MULTILINE)
            if name_match:
                name = name_match.group(1).strip().strip('"').strip("'")

            description = scorer._extract_description(content)
            tokens = scorer._tokenize_meaningful(
                description.lower(), expand_reverse=True
            ) if description else []

            content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]

            skills.append({
                "path": str(skill_md),
                "name": name,
                "description": description,
                "content_hash": content_hash,
                "tokens": tokens,
                "content": content,
            })

    return skills


# --- TF-IDF Cosine Similarity ---

def _compute_tfidf_vectors(skills: list[dict]) -> tuple[dict, dict]:
    """Compute TF-IDF vectors for all skills.

    Returns:
        (tfidf_vectors, document_frequencies)
        tfidf_vectors: {skill_index: {term: tfidf_weight}}
        document_frequencies: {term: num_skills_containing_term}
    """
    n_docs = len(skills)
    if n_docs == 0:
        return {}, {}

    # Document frequency
    df = defaultdict(int)
    for skill in skills:
        unique_tokens = set(skill["tokens"])
        for token in unique_tokens:
            df[token] += 1

    # TF-IDF vectors
    vectors = {}
    for i, skill in enumerate(skills):
        tf = defaultdict(int)
        for token in skill["tokens"]:
            tf[token] += 1

        vector = {}
        for term, count in tf.items():
            tf_val = count / max(len(skill["tokens"]), 1)
            idf_val = math.log(n_docs / (df[term] + 1)) + 1
            vector[term] = tf_val * idf_val
        vectors[i] = vector

    return vectors, dict(df)


def _cosine_similarity(v1: dict, v2: dict) -> float:
    """Compute cosine similarity between two sparse TF-IDF vectors."""
    common_terms = set(v1.keys()) & set(v2.keys())
    if not common_terms:
        return 0.0

    dot = sum(v1[t] * v2[t] for t in common_terms)
    norm1 = math.sqrt(sum(v ** 2 for v in v1.values()))
    norm2 = math.sqrt(sum(v ** 2 for v in v2.values()))

    if norm1 == 0 or norm2 == 0:
        return 0.0

    return dot / (norm1 * norm2)


def detect_trigger_overlaps(skills: list[dict]) -> list[dict]:
    """Detect pairwise trigger overlap using TF-IDF cosine similarity.

    Thresholds: >=0.70 critical, 0.45-0.69 warning, 0.20-0.44 info
    """
    vectors, _ = _compute_tfidf_vectors(skills)
    overlaps = []

    for i in range(len(skills)):
        for j in range(i + 1, len(skills)):
            if i not in vectors or j not in vectors:
                continue

            sim = _cosine_similarity(vectors[i], vectors[j])
            if sim < 0.20:
                continue

            # Find overlapping terms
            common = set(vectors[i].keys()) & set(vectors[j].keys())

            if sim >= 0.70:
                severity = "critical"
            elif sim >= 0.45:
                severity = "warning"
            else:
                severity = "info"

            overlaps.append({
                "type": "trigger_overlap",
                "severity": severity,
                "skill_a": skills[i]["name"],
                "skill_a_path": skills[i]["path"],
                "skill_b": skills[j]["name"],
                "skill_b_path": skills[j]["path"],
                "similarity": round(sim, 3),
                "common_terms": sorted(common)[:10],
            })

    return overlaps


# --- Broken Handoff Detection ---

def _levenshtein_distance(s1: str, s2: str) -> int:
    """Simple Levenshtein distance for fuzzy matching."""
    if len(s1) < len(s2):
        return _levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)

    prev_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr_row = [i + 1]
        for j, c2 in enumerate(s2):
            cost = 0 if c1 == c2 else 1
            curr_row.append(min(
                curr_row[j] + 1,
                prev_row[j + 1] + 1,
                prev_row[j] + cost,
            ))
        prev_row = curr_row

    return prev_row[-1]


def detect_broken_handoffs(skills: list[dict]) -> list[dict]:
    """Detect references to skills that don't exist in the mesh."""
    # Build name resolution table
    name_table = {}
    for skill in skills:
        name = skill["name"].lower()
        name_table[name] = skill
        # Also register slug variants
        slug = re.sub(r"[^a-z0-9]+", "-", name).strip("-")
        name_table[slug] = skill
        # And underscore variant
        name_table[slug.replace("-", "_")] = skill

    # Handoff patterns
    handoff_pattern = re.compile(
        r"(?:use|hand\s*off\s*to|then\s+use|pass\s+to|chain\s+with|"
        r"followed\s+by|after\s+.*use|before\s+.*use|instead\s+use|"
        r"suggest\s+using|complementary\s+.*skill|works\s+with)\s+"
        r"[`'\"]?([a-zA-Z][a-zA-Z0-9_-]+(?:\s+[a-zA-Z0-9_-]+)?)[`'\"]?",
        re.IGNORECASE
    )

    # Also match /slash-command references
    slash_pattern = re.compile(r"/([a-zA-Z][a-zA-Z0-9_-]+(?::[a-zA-Z0-9_-]+)?)")

    issues = []

    for skill in skills:
        content = skill.get("content", "")

        # Find handoff references
        refs = set()
        # Common words that aren't skill names
        _false_positives = {
            "this", "that", "the", "a", "an", "it", "your", "my",
            "constraints to", "results", "history", "data", "mode",
            "another", "other", "same", "different", "each", "all",
            "first", "next", "last", "new", "old", "any", "every",
            "for brand-new", "discovery mode", "parallel mode",
            "sequential mode", "analyze-skill", "current best",
        }
        for match in handoff_pattern.finditer(content):
            ref = match.group(1).strip().lower()
            if ref in _false_positives:
                continue
            # Skip refs that are too short or too generic
            if len(ref) < 3 or ref.isdigit():
                continue
            refs.add(ref)

        for match in slash_pattern.finditer(content):
            ref = match.group(1).strip().lower()
            # Only consider base skill name from slash commands (skip subcommands)
            if ":" in ref:
                base = ref.split(":")[0]
                # Skip self-references via slash commands
                if base != skill["name"].lower():
                    refs.add(base)

        # Check each reference against name table
        for ref in refs:
            # Skip self-references
            if ref == skill["name"].lower():
                continue

            if ref in name_table:
                continue  # Valid reference

            # Fuzzy match
            suggestion = None
            for known_name in name_table:
                if _levenshtein_distance(ref, known_name) <= 2:
                    suggestion = name_table[known_name]["name"]
                    break

            issues.append({
                "type": "broken_handoff",
                "severity": "warning",
                "skill": skill["name"],
                "skill_path": skill["path"],
                "referenced": ref,
                "suggestion": suggestion,
            })

    return issues


# --- Scope Collision Detection ---

# Domain keyword mapping
_DOMAIN_KEYWORDS = {
    "devops": ["deploy", "docker", "kubernetes", "ci/cd", "pipeline", "infrastructure", "terraform", "helm"],
    "testing": ["test", "spec", "assertion", "mock", "fixture", "coverage", "jest", "pytest"],
    "quality": ["lint", "format", "quality", "review", "audit", "standards", "convention"],
    "backend": ["api", "server", "database", "endpoint", "rest", "graphql", "microservice"],
    "frontend": ["react", "component", "css", "html", "ui", "layout", "style", "tailwind"],
    "security": ["auth", "security", "vulnerability", "credential", "encrypt", "token", "permission"],
    "data": ["data", "analytics", "pipeline", "etl", "transform", "schema", "migration"],
    "docs": ["documentation", "readme", "guide", "tutorial", "api-doc", "changelog"],
    "ai": ["llm", "prompt", "model", "embedding", "agent", "ai", "ml", "inference"],
    "skill": ["skill", "improve", "trigger", "eval", "score", "iterate", "forge"],
}


def _classify_domain(skill: dict) -> dict[str, float]:
    """Classify a skill into domains based on keyword matching.

    Returns dict of domain -> relevance score.
    """
    text = (skill.get("description", "") + " " + skill.get("name", "")).lower()
    tokens = set(scorer._tokenize_meaningful(text, expand_reverse=True))

    domains = {}
    for domain, keywords in _DOMAIN_KEYWORDS.items():
        overlap = sum(1 for kw in keywords if kw in tokens or any(kw in t for t in tokens))
        if overlap > 0:
            domains[domain] = overlap / len(keywords)

    return domains


def detect_scope_collisions(skills: list[dict]) -> list[dict]:
    """Detect skills with overlapping primary domains and positive scope overlap."""
    # Classify all skills
    skill_domains = []
    for skill in skills:
        domains = _classify_domain(skill)
        primary = max(domains, key=domains.get) if domains else None
        skill_domains.append({
            "skill": skill,
            "domains": domains,
            "primary": primary,
        })

    collisions = []

    for i in range(len(skill_domains)):
        for j in range(i + 1, len(skill_domains)):
            sd_i = skill_domains[i]
            sd_j = skill_domains[j]

            # Both need a primary domain and they must match
            if not sd_i["primary"] or not sd_j["primary"]:
                continue
            if sd_i["primary"] != sd_j["primary"]:
                continue

            # Check scope overlap via token overlap
            tokens_i = set(skills[i].get("tokens", []))
            tokens_j = set(skills[j].get("tokens", []))
            if not tokens_i or not tokens_j:
                continue

            overlap = len(tokens_i & tokens_j)
            union = len(tokens_i | tokens_j)
            jaccard = overlap / union if union > 0 else 0

            if jaccard < 0.20:
                continue

            severity = "critical" if jaccard >= 0.50 else "warning" if jaccard >= 0.35 else "info"

            collisions.append({
                "type": "scope_collision",
                "severity": severity,
                "skill_a": skills[i]["name"],
                "skill_a_path": skills[i]["path"],
                "skill_b": skills[j]["name"],
                "skill_b_path": skills[j]["path"],
                "shared_domain": sd_i["primary"],
                "overlap_score": round(jaccard, 3),
            })

    return collisions


# --- Mesh Health Score ---

def compute_mesh_health(issues: list[dict]) -> dict:
    """Compute mesh health score starting from 100, subtracting penalties.

    Penalties (each capped):
    - Critical conflicts: 15 each (max 60)
    - Warnings: 5 each (max 30)
    - Broken handoffs: 8 each (max 40)
    - Critical collisions: 12 each (max 48)
    """
    score = 100

    critical_conflicts = sum(1 for i in issues if i["type"] == "trigger_overlap" and i["severity"] == "critical")
    warnings = sum(1 for i in issues if i["severity"] == "warning")
    broken_handoffs = sum(1 for i in issues if i["type"] == "broken_handoff")
    critical_collisions = sum(1 for i in issues if i["type"] == "scope_collision" and i["severity"] == "critical")

    score -= min(critical_conflicts * 15, 60)
    score -= min(warnings * 5, 30)
    score -= min(broken_handoffs * 8, 40)
    score -= min(critical_collisions * 12, 48)

    return {
        "score": max(0, score),
        "critical_conflicts": critical_conflicts,
        "warnings": warnings,
        "broken_handoffs": broken_handoffs,
        "critical_collisions": critical_collisions,
        "total_issues": len(issues),
    }


# --- Cache for Incremental Mode ---

def _load_cache(cache_path: Path) -> dict:
    """Load incremental cache."""
    if cache_path.exists():
        try:
            return json.loads(cache_path.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_cache(cache_path: Path, cache: dict):
    """Save incremental cache."""
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, indent=2))


# --- Main ---

def run_mesh_analysis(
    skill_dirs: list[str],
    severity_filter: Optional[str] = None,
    incremental: bool = False,
) -> dict:
    """Run full mesh analysis.

    Returns dict with: skills, issues, health, summary.
    """
    # Default dirs
    if not skill_dirs:
        skill_dirs = [
            str(Path.home() / ".claude" / "skills"),
            ".claude/skills",
        ]

    skills = discover_skills(skill_dirs)

    if not skills:
        return {
            "skills_found": 0,
            "issues": [],
            "health": {"score": 100, "total_issues": 0},
            "summary": "No skills found in scanned directories.",
        }

    # Run all detectors
    issues = []
    issues.extend(detect_trigger_overlaps(skills))
    issues.extend(detect_broken_handoffs(skills))
    issues.extend(detect_scope_collisions(skills))

    # Filter by severity
    severity_order = {"info": 0, "warning": 1, "critical": 2}
    if severity_filter and severity_filter in severity_order:
        min_severity = severity_order[severity_filter]
        issues = [i for i in issues if severity_order.get(i.get("severity", "info"), 0) >= min_severity]

    # Sort by severity descending
    issues.sort(key=lambda i: severity_order.get(i.get("severity", "info"), 0), reverse=True)

    health = compute_mesh_health(issues)

    return {
        "skills_found": len(skills),
        "skill_names": [s["name"] for s in skills],
        "issues": issues,
        "health": health,
    }


def format_mesh_report(result: dict) -> str:
    """Format mesh analysis as human-readable text."""
    lines = []
    lines.append("=" * 70)
    lines.append("  SkillForge Skill Mesh — Health Report")
    lines.append("=" * 70)
    lines.append("")

    health = result.get("health", {})
    score = health.get("score", 100)
    total_issues = health.get("total_issues", 0)

    indicator = "\u2713" if score >= 80 else "\u25b3" if score >= 50 else "\u2717"
    lines.append(f"  {indicator} Mesh Health Score: {score}/100")
    lines.append(f"  Skills scanned: {result.get('skills_found', 0)}")
    lines.append(f"  Issues found: {total_issues}")
    lines.append("")

    if result.get("skill_names"):
        lines.append("  Skills in mesh:")
        for name in sorted(result["skill_names"]):
            lines.append(f"    - {name}")
        lines.append("")

    issues = result.get("issues", [])
    if issues:
        lines.append("  Issues:")
        lines.append("  " + "-" * 60)
        for issue in issues:
            sev = issue.get("severity", "info").upper()
            itype = issue.get("type", "unknown")

            if itype == "trigger_overlap":
                lines.append(
                    f"  [{sev}] Trigger overlap: {issue['skill_a']} <-> {issue['skill_b']}"
                    f" (similarity: {issue['similarity']:.1%})"
                )
                if issue.get("common_terms"):
                    lines.append(f"         Common terms: {', '.join(issue['common_terms'][:5])}")
            elif itype == "broken_handoff":
                suggestion = f" (did you mean: {issue['suggestion']}?)" if issue.get("suggestion") else ""
                lines.append(
                    f"  [{sev}] Broken handoff: {issue['skill']} references '{issue['referenced']}'"
                    f" — not found{suggestion}"
                )
            elif itype == "scope_collision":
                lines.append(
                    f"  [{sev}] Scope collision: {issue['skill_a']} <-> {issue['skill_b']}"
                    f" (domain: {issue['shared_domain']}, overlap: {issue['overlap_score']:.1%})"
                )
            lines.append("")
    else:
        lines.append("  No issues found — mesh is healthy!")
        lines.append("")

    lines.append("=" * 70)
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="SkillForge Skill Mesh Analyzer")
    parser.add_argument("--skill-dirs", nargs="+", default=[], help="Directories to scan for SKILL.md files")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--incremental", action="store_true", help="Use cached tokens (recompute only changed skills)")
    parser.add_argument("--severity", choices=["info", "warning", "critical"], default=None,
                        help="Minimum severity to report")
    args = parser.parse_args()

    result = run_mesh_analysis(
        skill_dirs=args.skill_dirs,
        severity_filter=args.severity,
        incremental=args.incremental,
    )

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(format_mesh_report(result))


if __name__ == "__main__":
    main()
