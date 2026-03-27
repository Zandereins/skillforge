#!/usr/bin/env python3
"""Schliff Drift Detector — Find Stale References in Instruction Files.

Scans instruction files for referenced paths, scripts, and targets,
then validates they still exist on disk.
"""
from __future__ import annotations

import json
import os
import re
import sys
from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# Regex patterns — all bounded, no nested quantifiers
# ---------------------------------------------------------------------------

# Backtick code spans containing path-like refs (dir/file.ext)
# Bounded: up to 200 chars inside backticks
_RE_BACKTICK_PATH = re.compile(
    r"`([A-Za-z0-9_./@-]{1,200})"   # path chars inside backtick
    r"`"
)

# Bare paths: word/word.ext patterns not inside backticks
# Must contain at least one `/` and end with a file extension
_RE_BARE_PATH = re.compile(
    r"(?<![`])"                              # not preceded by backtick
    r"([A-Za-z0-9_.-]{1,100}"               # first segment
    r"(?:/[A-Za-z0-9_.-]{1,100}){1,20}"     # at least one /segment
    r"\.[A-Za-z0-9]{1,10})"                  # file extension
    r"(?![`])"                               # not followed by backtick
)

# npm run <script> or yarn <script>
_RE_NPM_SCRIPT = re.compile(
    r"(?:npm\s+run|yarn)\s+([A-Za-z0-9_:.-]{1,80})"
)

# make <target>
_RE_MAKE_TARGET = re.compile(
    r"make\s+([A-Za-z0-9_.-]{1,80})"
)

# File extension check for filtering path candidates
_RE_HAS_EXTENSION = re.compile(r"\.[A-Za-z0-9]{1,10}$")

# Strip backtick spans for bare-path scanning
_RE_BACKTICK_SPAN = re.compile(r"`[^`]*`")


def _is_plausible_path(candidate: str) -> bool:
    """Return True if the candidate looks like a real file path."""
    if "/" not in candidate:
        return False
    if not _RE_HAS_EXTENSION.search(candidate):
        return False
    # Reject URLs
    if candidate.startswith(("http://", "https://", "ftp://")):
        return False
    # Reject absolute paths and parent traversals
    if candidate.startswith("/") or candidate.startswith(".."):
        return False
    # Reject domain-like refs (e.g. example.com/path)
    first_segment = candidate.split("/")[0]
    if "." in first_segment and not first_segment.startswith("."):
        # Looks like a domain (e.g. example.com), not a path
        return False
    return True


def extract_references(content: str) -> List[Dict[str, object]]:
    """Extract file paths, script references, and make targets from content.

    Scans for:
    - Paths inside backtick code spans (e.g. `src/main.py`)
    - Bare paths with `/` and a file extension
    - npm run / yarn commands
    - make targets

    Returns a deduplicated list of dicts with keys: ref, type, line.
    """
    seen: set[tuple[str, str]] = set()
    results: List[Dict[str, object]] = []
    lines = content.splitlines()

    for line_num, line in enumerate(lines, start=1):
        # Backtick paths
        for m in _RE_BACKTICK_PATH.finditer(line):
            candidate = m.group(1)
            if _is_plausible_path(candidate):
                key = (candidate, "path")
                if key not in seen:
                    seen.add(key)
                    results.append({
                        "ref": candidate,
                        "type": "path",
                        "line": line_num,
                    })

        # Bare paths — search in line with backtick spans removed
        line_no_backticks = _RE_BACKTICK_SPAN.sub("", line)
        for m in _RE_BARE_PATH.finditer(line_no_backticks):
            candidate = m.group(1)
            if _is_plausible_path(candidate):
                key = (candidate, "path")
                if key not in seen:
                    seen.add(key)
                    results.append({
                        "ref": candidate,
                        "type": "path",
                        "line": line_num,
                    })

        # npm/yarn scripts
        for m in _RE_NPM_SCRIPT.finditer(line):
            script_name = m.group(1)
            key = (script_name, "script")
            if key not in seen:
                seen.add(key)
                results.append({
                    "ref": script_name,
                    "type": "script",
                    "line": line_num,
                })

        # make targets
        for m in _RE_MAKE_TARGET.finditer(line):
            target = m.group(1)
            key = (target, "make_target")
            if key not in seen:
                seen.add(key)
                results.append({
                    "ref": target,
                    "type": "make_target",
                    "line": line_num,
                })

    return results


def _load_package_json_scripts(repo_root: str) -> Optional[Dict[str, str]]:
    """Load scripts from package.json if it exists. Returns None if absent."""
    pkg_path = os.path.join(repo_root, "package.json")
    if not os.path.isfile(pkg_path):
        return None
    try:
        with open(pkg_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("scripts", {})
    except (json.JSONDecodeError, OSError) as exc:
        print(f"Warning: could not parse package.json: {exc}", file=sys.stderr)
        return None


def _load_makefile_targets(repo_root: str) -> Optional[set[str]]:
    """Extract target names from Makefile if it exists. Returns None if absent."""
    makefile_path = os.path.join(repo_root, "Makefile")
    if not os.path.isfile(makefile_path):
        return None
    try:
        with open(makefile_path, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError as exc:
        print(f"Warning: could not read Makefile: {exc}", file=sys.stderr)
        return None

    targets: set[str] = set()
    # Match lines like "target-name:" at start of line (bounded)
    for m in re.finditer(r"^([A-Za-z0-9_.-]{1,80}):", content, re.MULTILINE):
        targets.add(m.group(1))
    return targets


def validate_references(
    refs: List[Dict[str, object]],
    repo_root: str,
) -> List[Dict[str, object]]:
    """Validate extracted references against the actual repo.

    For each reference:
    - type "path": checks if the file/dir exists under repo_root
    - type "script": checks if the script exists in package.json
    - type "make_target": checks if the target exists in Makefile

    Returns a list of findings with added "status" and "detail" keys.
    """
    findings: List[Dict[str, object]] = []

    # Lazy-load external files only when needed
    pkg_scripts: Optional[Dict[str, str]] = None
    pkg_scripts_loaded = False
    make_targets: Optional[set[str]] = None
    make_targets_loaded = False

    for ref_entry in refs:
        ref = ref_entry["ref"]
        ref_type = ref_entry["type"]
        line = ref_entry["line"]

        if ref_type == "path":
            full_path = os.path.normpath(os.path.join(repo_root, str(ref)))
            repo_abs = os.path.realpath(repo_root)
            if not full_path.startswith(repo_abs + os.sep) and full_path != repo_abs:
                findings.append({
                    "ref": ref,
                    "type": ref_type,
                    "line": line,
                    "status": "invalid",
                    "detail": "path escapes repo root",
                })
                continue
            if os.path.exists(full_path):
                findings.append({
                    "ref": ref,
                    "type": ref_type,
                    "line": line,
                    "status": "valid",
                    "detail": f"exists at {full_path}",
                })
            else:
                findings.append({
                    "ref": ref,
                    "type": ref_type,
                    "line": line,
                    "status": "missing",
                    "detail": f"not found: {full_path}",
                })

        elif ref_type == "script":
            if not pkg_scripts_loaded:
                pkg_scripts = _load_package_json_scripts(repo_root)
                pkg_scripts_loaded = True

            if pkg_scripts is None:
                findings.append({
                    "ref": ref,
                    "type": ref_type,
                    "line": line,
                    "status": "missing",
                    "detail": "no package.json found",
                })
            elif str(ref) in pkg_scripts:
                findings.append({
                    "ref": ref,
                    "type": ref_type,
                    "line": line,
                    "status": "valid",
                    "detail": f"script defined in package.json",
                })
            else:
                findings.append({
                    "ref": ref,
                    "type": ref_type,
                    "line": line,
                    "status": "missing",
                    "detail": f"script not in package.json",
                })

        elif ref_type == "make_target":
            if not make_targets_loaded:
                make_targets = _load_makefile_targets(repo_root)
                make_targets_loaded = True

            if make_targets is None:
                findings.append({
                    "ref": ref,
                    "type": ref_type,
                    "line": line,
                    "status": "missing",
                    "detail": "no Makefile found",
                })
            elif str(ref) in make_targets:
                findings.append({
                    "ref": ref,
                    "type": ref_type,
                    "line": line,
                    "status": "valid",
                    "detail": f"target defined in Makefile",
                })
            else:
                findings.append({
                    "ref": ref,
                    "type": ref_type,
                    "line": line,
                    "status": "missing",
                    "detail": f"target not in Makefile",
                })

    return findings


def generate_drift_report(findings: List[Dict[str, object]]) -> str:
    """Format a human-readable drift report from validation findings.

    Groups results by status (missing first), shows counts, and lists
    each missing reference with its type and line number.

    Returns an empty string if there are no findings.
    """
    if not findings:
        return ""

    missing = [f for f in findings if f["status"] == "missing"]
    valid = [f for f in findings if f["status"] == "valid"]
    total = len(findings)

    lines: list[str] = []
    lines.append("=== Schliff Drift Report ===")
    lines.append(f"References checked: {total}")
    lines.append(f"Missing: {len(missing)}")
    lines.append(f"Valid: {len(valid)}")
    lines.append("")

    if missing:
        lines.append("--- Missing References ---")
        for f in missing:
            lines.append(
                f"  L{f['line']}: [{f['type']}] {f['ref']}"
                f" — {f['detail']}"
            )
        lines.append("")

    if valid:
        lines.append("--- Valid References ---")
        for f in valid:
            lines.append(
                f"  L{f['line']}: [{f['type']}] {f['ref']}"
            )
        lines.append("")

    return "\n".join(lines)
