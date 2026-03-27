#!/usr/bin/env python3
"""Schliff CLI — The finishing cut for Claude Code skills.

Usage:
    schliff score <path>             Score a SKILL.md file
    schliff compare <file_a> <file_b> Compare two files side by side
    schliff diff <path>              Explain score changes between git commits
    schliff verify <path>            CI gate — exit 0 if pass, 1 if fail
    schliff doctor                   Scan all installed skills
    schliff report <path>            Generate Markdown score report
    schliff badge <path>             Generate markdown badge
    schliff suggest <path>           Suggest ranked fixes with estimated score impact
    schliff demo                     Score a built-in bad skill
    schliff version                  Show version
"""
from __future__ import annotations

import sys
import os
import json
import argparse
import urllib.parse

# Ensure scripts dir is on sys.path so existing modules (scoring, shared, etc.)
# can be imported without restructuring the project.
_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)


def _load_eval_suite_from_args(args: argparse.Namespace) -> "dict | None":
    """Load eval suite from --eval-suite flag or auto-discover from skill dir."""
    from pathlib import Path
    from shared import load_eval_suite, MAX_SKILL_SIZE

    if getattr(args, "eval_suite", None):
        eval_path = Path(args.eval_suite)
        if not eval_path.exists():
            print(f"Error: eval-suite not found: {args.eval_suite}", file=sys.stderr)
            sys.exit(1)
        if eval_path.stat().st_size > MAX_SKILL_SIZE:
            print(f"Error: eval-suite exceeds {MAX_SKILL_SIZE} byte size limit", file=sys.stderr)
            sys.exit(1)
        try:
            return json.loads(eval_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(f"Error: malformed eval-suite: {e}", file=sys.stderr)
            sys.exit(1)
    skill_path = getattr(args, "skill_path", None)
    if skill_path:
        return load_eval_suite(skill_path)
    return None


def cmd_score(args: argparse.Namespace) -> None:
    """Score a single SKILL.md file (structural + runtime when eval suite available)."""
    import tempfile
    from pathlib import Path
    from scoring import compute_composite
    from shared import build_scores, fetch_url_safe

    skill_path = getattr(args, "skill_path", None)
    url = getattr(args, "url", None)

    # Validate that exactly one of skill_path or --url is provided
    if not skill_path and not url:
        print("Error: provide a skill path or --url", file=sys.stderr)
        sys.exit(1)
    if skill_path and url:
        print("Error: skill_path and --url are mutually exclusive", file=sys.stderr)
        sys.exit(1)

    tmp_path: "str | None" = None
    display_source: str

    try:
        if url:
            # Fetch URL content into a tempfile
            try:
                content = fetch_url_safe(url)
            except ValueError as exc:
                print(f"Error: {exc}", file=sys.stderr)
                sys.exit(1)

            # Derive a filename from the URL path for format detection
            url_filename = Path(urllib.parse.urlparse(url).path).name or "SKILL.md"
            # Detect format from URL filename (not tempfile name)
            from scoring.formats import detect_format as _detect_fmt
            url_fmt = _detect_fmt(url_filename)
            suffix = Path(url_filename).suffix or ".md"
            tmp = tempfile.NamedTemporaryFile(
                mode="w", suffix=suffix, delete=False, encoding="utf-8",
                prefix=Path(url_filename).stem + "_",
            )
            tmp.write(content)
            tmp.close()
            tmp_path = tmp.name
            skill_path = tmp_path
            display_source = url
        else:
            url_fmt = None
            if not Path(skill_path).exists():
                print(f"Error: file not found: {skill_path}", file=sys.stderr)
                sys.exit(1)
            display_source = skill_path

        eval_suite = _load_eval_suite_from_args(args)
        fmt_override = getattr(args, "format", None)
        # For --url, use format detected from URL filename (not tempfile name)
        effective_fmt = fmt_override or url_fmt
        scores = build_scores(skill_path, eval_suite, include_runtime=True, fmt=effective_fmt)

        # Determine the effective format for display
        if effective_fmt:
            detected_fmt = effective_fmt
        else:
            from scoring.formats import detect_format
            detected_fmt = detect_format(skill_path)

        composite = compute_composite(scores)

        # Token budget check — reuse cached content from shared.read_skill_safe
        from scoring.formats import estimate_tokens, check_token_budget
        from shared import read_skill_safe
        try:
            skill_content = read_skill_safe(skill_path)
        except (OSError, ValueError) as exc:
            print(f"Error: could not read {display_source}: {exc}", file=sys.stderr)
            sys.exit(1)
        token_info = check_token_budget(skill_content, detected_fmt)

        if getattr(args, "json", False):
            result = {
                "skill_path": display_source,
                "format": detected_fmt,
                "composite_score": composite["score"],
                "dimensions": {k: round(v["score"], 1) if isinstance(v["score"], float) else v["score"] for k, v in scores.items()},
                "warnings": composite["warnings"],
                "token_budget": token_info,
            }
            print(json.dumps(result, indent=2))
        else:
            from terminal_art import format_score_display
            import text_gradient

            # Extract contradictions from clarity details
            clarity_data = scores.get("clarity", {})
            contradictions = clarity_data.get("details", {}).get("contradictions", [])

            # Count available deterministic fixes
            try:
                gradients = text_gradient.compute_gradients(
                    skill_path, eval_suite, include_clarity=True,
                )
                fix_count = len(gradients)
            except Exception as exc:
                print(f"Warning: could not compute fix count: {exc}", file=sys.stderr)
                fix_count = 0

            # Get version
            try:
                from importlib.metadata import version, PackageNotFoundError
                ver = version("schliff")
            except PackageNotFoundError:
                ver = "dev"

            output = format_score_display(
                scores=scores,
                composite=composite,
                version=ver,
                contradictions=contradictions if contradictions else None,
                fix_count=fix_count,
            )
            print(output)

            # Token budget line
            from terminal_art import is_color_tty, RESET
            tok = token_info["tokens"]
            bud = token_info["budget"]
            if is_color_tty():
                sev = token_info["severity"]
                if sev == "ok":
                    color = "\x1b[32m"   # green
                elif sev == "warning":
                    color = "\x1b[33m"   # yellow
                else:
                    color = "\x1b[31m"   # red for over
                print(f"  Tokens: {color}{tok:,}{RESET} / {bud:,} ({sev})")
            else:
                print(f"  Tokens: {tok:,} / {bud:,} ({token_info['severity']})")

            # --tokens: section breakdown
            if getattr(args, "tokens", False):
                lines = skill_content.splitlines()
                sections: list[tuple[str, int]] = []
                current_section = "(preamble)"
                section_start = 0
                for i, line in enumerate(lines):
                    if line.startswith("# ") or line.startswith("## "):
                        if i > section_start:
                            sec_content = "\n".join(lines[section_start:i])
                            sections.append((current_section, estimate_tokens(sec_content)))
                        current_section = line.lstrip("#").strip()
                        section_start = i
                # Last section
                sec_content = "\n".join(lines[section_start:])
                sections.append((current_section, estimate_tokens(sec_content)))

                print("\n  Token Breakdown by Section:")
                for name, count in sections:
                    print(f"    {name:<40s} {count:>6,} tokens")

            if url:
                print(f"  Source: {url}")
            if detected_fmt != "skill.md":
                print(f"  Format: {detected_fmt} (normalized)")

    finally:
        if tmp_path is not None:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def cmd_verify(args: argparse.Namespace) -> None:
    """CI gate — score a skill and exit with appropriate code."""
    from pathlib import Path
    from shared import load_eval_suite, MAX_SKILL_SIZE
    import verify as verify_mod

    if not Path(args.skill_path).exists():
        print(f"Error: file not found: {args.skill_path}", file=sys.stderr)
        sys.exit(2)

    eval_suite = None
    if args.eval_suite:
        eval_path = Path(args.eval_suite)
        if not eval_path.exists():
            print(f"Error: eval-suite not found: {args.eval_suite}", file=sys.stderr)
            sys.exit(2)
        if eval_path.stat().st_size > MAX_SKILL_SIZE:
            print(f"Error: eval-suite exceeds {MAX_SKILL_SIZE} byte size limit", file=sys.stderr)
            sys.exit(2)
        try:
            eval_suite = json.loads(eval_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(f"Error: malformed eval-suite: {e}", file=sys.stderr)
            sys.exit(2)
    else:
        eval_suite = load_eval_suite(args.skill_path)

    try:
        verdict = verify_mod.run_verify(
            skill_path=args.skill_path,
            min_score=args.min_score,
            check_regression=args.regression,
            history_path=args.history,
            eval_suite=eval_suite,
        )
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(2)

    if getattr(args, "json", False):
        print(json.dumps(verdict, indent=2))
    else:
        print(verify_mod.format_verdict(verdict))

    sys.exit(verdict["exit_code"])


def cmd_doctor(args: argparse.Namespace) -> None:
    """Run doctor scan across all installed skills."""
    import doctor as doctor_mod

    verbose = getattr(args, "verbose", False)
    repo_root = getattr(args, "repo", None)
    report = doctor_mod.run_doctor(
        skill_dirs=getattr(args, "skill_dirs", None),
        verbose=verbose,
        repo_root=repo_root,
    )

    if getattr(args, "json", False):
        print(json.dumps(report, indent=2))
    else:
        formatted = doctor_mod.format_doctor_report(report, verbose=verbose)
        print(formatted)


def cmd_badge(args: argparse.Namespace) -> None:
    """Generate a markdown badge for a skill's score."""
    import urllib.parse
    from pathlib import Path
    from scoring import compute_composite
    from shared import build_scores
    from terminal_art import score_to_grade

    if not Path(args.skill_path).exists():
        print(f"Error: file not found: {args.skill_path}", file=sys.stderr)
        sys.exit(1)

    eval_suite = _load_eval_suite_from_args(args)
    scores = build_scores(args.skill_path, eval_suite)

    composite = compute_composite(scores)
    score = composite["score"]
    grade = score_to_grade(score)

    colors = {
        "S": "brightgreen", "A": "green", "B": "yellowgreen",
        "C": "yellow", "D": "orange", "E": "red", "F": "red",
    }
    color = colors.get(grade, "lightgrey")

    label = urllib.parse.quote(f"{score:.0f}/100 [{grade}]", safe="")
    badge_md = f"[![Schliff: {score:.0f} [{grade}]](https://img.shields.io/badge/Schliff-{label}-{color})](https://github.com/Zandereins/schliff)"

    print(badge_md)


def cmd_demo(_args: argparse.Namespace) -> None:
    """Score a built-in demo skill to showcase schliff's output."""
    import tempfile
    from pathlib import Path

    demo_content = '''---
name: deploy-helper
description: Helps with deployment stuff
---

# Deploy Helper

This skill probably helps with deployment. You might want to use it when deploying things.

## What It Does

- Setting up deployment configurations
- Running deploy commands
- Checking if deployment worked

## How To Use

1. Tell Claude you want to deploy something
2. It will try to help you
3. Check if it worked
'''

    with tempfile.TemporaryDirectory() as tmpdir:
        skill_path = str(Path(tmpdir) / "SKILL.md")
        Path(skill_path).write_text(demo_content, encoding="utf-8")

        # Reuse cmd_score logic
        import argparse as _ap
        fake_args = _ap.Namespace(skill_path=skill_path, json=False, eval_suite=None, url=None, format=None, tokens=False)
        cmd_score(fake_args)

    print("\n  This is a deliberately bad skill. Try schliff on your own skills!")
    print("  Usage: schliff score path/to/SKILL.md\n")


def cmd_diff(args: argparse.Namespace) -> None:
    """Explain score changes between git commits."""
    import re
    import subprocess
    import tempfile
    from pathlib import Path
    from scoring import compute_composite
    from scoring.diff import score_diff, explain_score_change
    from shared import build_scores, MAX_SKILL_SIZE

    skill_path = args.skill_path
    if not Path(skill_path).exists():
        print(f"Error: file not found: {skill_path}", file=sys.stderr)
        sys.exit(1)

    ref = args.ref

    # Validate ref to prevent git flag injection
    if ref.startswith("-") or not re.match(r'^[a-zA-Z0-9_.~^@/\-]+$', ref):
        print(f"Error: invalid git reference: {ref}", file=sys.stderr)
        sys.exit(1)

    # Score current version
    eval_suite = _load_eval_suite_from_args(args)
    new_scores = build_scores(skill_path, eval_suite)
    new_composite = compute_composite(new_scores)

    # Reconstruct old version via git show
    try:
        # Get the path relative to git root
        git_root = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=5,
        )
        if git_root.returncode != 0:
            print("Error: not a git repository", file=sys.stderr)
            sys.exit(1)

        abs_skill = str(Path(skill_path).resolve())
        root = git_root.stdout.strip()

        # Ensure skill path is inside the git repository
        if not abs_skill.startswith(root + os.sep):
            print("Error: skill path must be inside the git repository", file=sys.stderr)
            sys.exit(1)

        rel_path = os.path.relpath(abs_skill, root)

        old_content = subprocess.run(
            ["git", "show", f"{ref}:{rel_path}"],
            capture_output=True, text=True, timeout=10,
        )
        if old_content.returncode != 0:
            print(f"Error: cannot read {rel_path} at ref '{ref}' — file may not exist in that commit", file=sys.stderr)
            sys.exit(1)

        # Guard against oversized content from git history
        if len(old_content.stdout) > MAX_SKILL_SIZE:
            print(f"Error: file at ref '{ref}' exceeds {MAX_SKILL_SIZE} byte size limit", file=sys.stderr)
            sys.exit(1)
    except FileNotFoundError:
        print("Error: git not available", file=sys.stderr)
        sys.exit(1)
    except subprocess.TimeoutExpired:
        print("Error: git command timed out", file=sys.stderr)
        sys.exit(1)

    # Score old version in a temp file
    with tempfile.TemporaryDirectory() as tmpdir:
        old_path = str(Path(tmpdir) / "SKILL.md")
        Path(old_path).write_text(old_content.stdout, encoding="utf-8")
        old_scores = build_scores(old_path, eval_suite)
        old_composite = compute_composite(old_scores)

    # Diff analysis (signal/noise classification) — use resolved path
    diff_analysis = score_diff(abs_skill, ref)

    # Build per-dimension deltas
    old_flat = {k: v["score"] for k, v in old_scores.items() if isinstance(v, dict)}
    new_flat = {k: v["score"] for k, v in new_scores.items() if isinstance(v, dict)}
    explanations = explain_score_change(old_flat, new_flat, diff_analysis)

    if getattr(args, "json", False):
        result = {
            "skill_path": skill_path,
            "ref": ref,
            "old_composite": old_composite["score"],
            "new_composite": new_composite["score"],
            "composite_delta": round(new_composite["score"] - old_composite["score"], 1),
            "dimensions": explanations,
        }
        if diff_analysis.get("available"):
            result["diff_summary"] = diff_analysis["net_change"]
        print(json.dumps(result, indent=2))
    else:
        from terminal_art import score_to_grade

        old_score = old_composite["score"]
        new_score = new_composite["score"]
        delta = new_score - old_score

        old_grade = score_to_grade(old_score)
        new_grade = score_to_grade(new_score)

        print(f"\n  schliff diff  {ref} → current\n")
        print(f"  Composite: {old_score:.1f} [{old_grade}] → {new_score:.1f} [{new_grade}]  ({delta:+.1f})\n")

        if explanations:
            for exp in explanations:
                arrow = "+" if exp["delta"] > 0 else ""
                print(f"  {exp['dimension']:16s}  {exp['old']:6.1f} → {exp['new']:6.1f}  ({arrow}{exp['delta']:.1f})")
            print()
        else:
            print("  No significant dimension changes.\n")

        if diff_analysis.get("available"):
            net = diff_analysis["net_change"]
            print(f"  Diff: {net['signal']:+d} signal, {net['noise']:+d} noise, {net['lines']:+d} lines total\n")


def cmd_compare(args: argparse.Namespace) -> None:
    """Score two files and show a side-by-side dimension comparison."""
    from pathlib import Path
    from scoring import compute_composite
    from shared import build_scores

    path_a = args.file_a
    path_b = args.file_b

    if not Path(path_a).exists():
        print(f"Error: file not found: {path_a}", file=sys.stderr)
        sys.exit(1)
    if not Path(path_b).exists():
        print(f"Error: file not found: {path_b}", file=sys.stderr)
        sys.exit(1)

    eval_suite = _load_eval_suite_from_args(args)

    scores_a = build_scores(path_a, eval_suite)
    scores_b = build_scores(path_b, eval_suite)

    composite_a = compute_composite(scores_a)
    composite_b = compute_composite(scores_b)

    score_a = composite_a["score"]
    score_b = composite_b["score"]

    # Collect dimension names present in both scores
    dims = [k for k in scores_a if isinstance(scores_a[k], dict) and "score" in scores_a[k]]

    # Per-dimension deltas: B - A
    deltas = {}
    for dim in dims:
        val_a = scores_a[dim]["score"]
        val_b = scores_b.get(dim, {}).get("score", 0.0)
        deltas[dim] = round(val_b - val_a, 1)

    # Biggest absolute gap
    if deltas:
        biggest_dim = max(deltas, key=lambda d: abs(deltas[d]))
        biggest_delta = deltas[biggest_dim]
    else:
        biggest_dim = ""
        biggest_delta = 0.0

    if getattr(args, "json", False):
        result = {
            "file_a": {
                "path": path_a,
                "composite": round(score_a, 1),
                "dimensions": {k: round(scores_a[k]["score"], 1) for k in dims},
            },
            "file_b": {
                "path": path_b,
                "composite": round(score_b, 1),
                "dimensions": {k: round(scores_b.get(k, {}).get("score", 0.0), 1) for k in dims},
            },
            "deltas": deltas,
            "biggest_gap": {"dimension": biggest_dim, "delta": biggest_delta},
        }
        print(json.dumps(result, indent=2))
        return

    from terminal_art import score_to_grade

    grade_a = score_to_grade(score_a)
    grade_b = score_to_grade(score_b)

    print()
    print("  schliff compare")
    print()
    print(f"  File A: {path_a}  [{grade_a}] {score_a:.1f}")
    print(f"  File B: {path_b}  [{grade_b}] {score_b:.1f}")
    print()

    # Column header + separator
    header = f"  {'Dimension':<16}{'A':>8}{'B':>8}{'Delta':>10}"
    separator = "  " + "─" * 41
    print(header)
    print(separator)

    for dim in dims:
        val_a = scores_a[dim]["score"]
        val_b = scores_b.get(dim, {}).get("score", 0.0)
        delta = deltas[dim]
        delta_str = f"{delta:+.1f}"
        marker = "  ← biggest gap" if dim == biggest_dim else ""
        print(f"  {dim:<16}{val_a:>8.1f}{val_b:>8.1f}{delta_str:>10}{marker}")

    print(separator)

    composite_delta = round(score_b - score_a, 1)
    composite_delta_str = f"{composite_delta:+.1f}"
    print(f"  {'Composite':<16}{score_a:>8.1f}{score_b:>8.1f}{composite_delta_str:>10}")
    print()

    if biggest_dim:
        direction = "B" if biggest_delta > 0 else "A"
        dim_label = biggest_dim
        print(f"  Biggest gap: {dim_label} ({biggest_delta:+.1f}) — {direction} has stronger {dim_label} coverage")
    print()


def cmd_suggest(args: argparse.Namespace) -> None:
    """Suggest ranked fixes with estimated score impact."""
    from pathlib import Path
    from scoring import compute_composite
    from shared import build_scores
    from terminal_art import score_to_grade
    import text_gradient

    if not Path(args.skill_path).exists():
        print(f"Error: file not found: {args.skill_path}", file=sys.stderr)
        sys.exit(1)

    eval_suite = _load_eval_suite_from_args(args)
    top_n = max(1, args.top)

    # Compute current score
    scores = build_scores(args.skill_path, eval_suite, include_runtime=True)
    composite = compute_composite(scores)
    current_score = composite["score"]
    current_grade = score_to_grade(current_score)

    # Get all ranked gradients (include clarity for full picture)
    try:
        gradients = text_gradient.compute_gradients(
            args.skill_path, eval_suite, include_clarity=True,
        )
    except Exception as exc:
        print(f"Error: failed to compute gradients: {exc}", file=sys.stderr)
        sys.exit(1)

    top_gradients = gradients[:top_n]

    # Estimated score after applying all top fixes
    total_delta = sum(g["delta"] for g in top_gradients)
    estimated_score = min(100.0, current_score + total_delta)
    estimated_grade = score_to_grade(estimated_score)

    if getattr(args, "json", False):
        result = {
            "skill_path": args.skill_path,
            "current_score": round(current_score, 1),
            "current_grade": current_grade,
            "estimated_score": round(estimated_score, 1),
            "estimated_grade": estimated_grade,
            "suggestions": [
                {
                    "rank": i + 1,
                    "delta": g["delta"],
                    "delta_display": g.get("delta_display", f"+{g['delta']:.1f}"),
                    "dimension": g["dimension"],
                    "instruction": g["instruction"],
                    "confidence": g.get("confidence", "medium"),
                }
                for i, g in enumerate(top_gradients)
            ],
        }
        print(json.dumps(result, indent=2))
        return

    print()
    print(f"  schliff suggest  {args.skill_path}")
    print()
    print("  TOP FIXES (estimated impact):")

    for i, g in enumerate(top_gradients, 1):
        delta_val = g["delta"]
        delta_display = g.get("delta_display", None)
        if delta_display:
            # Range like "~2.0-5.0" — show midpoint with tilde
            delta_label = f"~{delta_val:.0f}"
        else:
            delta_label = f"+{delta_val:.0f}"
        print(f"  {i:2d}. [{delta_label:>4}] {g['instruction']}")

    print()
    print(
        f"  Current: {current_score:.1f} [{current_grade}]"
        f"  →  Estimated after fixes: ~{estimated_score:.1f} [{estimated_grade}]"
    )
    print()


def cmd_report(args: argparse.Namespace) -> None:
    """Generate a Markdown score report, optionally upload as GitHub Gist."""
    from pathlib import Path
    from scoring import compute_composite
    from shared import build_scores
    from terminal_art import score_to_grade
    import report as report_mod

    if not Path(args.skill_path).exists():
        print(f"Error: file not found: {args.skill_path}", file=sys.stderr)
        sys.exit(1)

    eval_suite = _load_eval_suite_from_args(args)
    scores = build_scores(args.skill_path, eval_suite, include_runtime=True)
    composite = compute_composite(scores)
    grade = score_to_grade(composite["score"])

    # Token budget for report — reuse cached content from shared.read_skill_safe
    from scoring.formats import detect_format, check_token_budget
    from shared import read_skill_safe
    detected_fmt = detect_format(args.skill_path)
    try:
        skill_content = read_skill_safe(args.skill_path)
    except (OSError, ValueError) as exc:
        print(f"Error: could not read {args.skill_path}: {exc}", file=sys.stderr)
        sys.exit(1)
    token_info = check_token_budget(skill_content, detected_fmt)

    markdown = report_mod.generate_report_markdown(
        scores=scores,
        skill_path=args.skill_path,
        composite=composite,
        grade=grade,
        token_info=token_info,
    )

    if getattr(args, "gist", False):
        url = report_mod.upload_gist(markdown)
        if url:
            print(f"Gist created: {url}")
        else:
            print(markdown)
    else:
        print(markdown)


def cmd_version(_args: argparse.Namespace) -> None:
    """Print version string."""
    try:
        from importlib.metadata import version, PackageNotFoundError
        print(f"schliff {version('schliff')}")
    except PackageNotFoundError:
        print("schliff dev")


def main():
    parser = argparse.ArgumentParser(
        prog="schliff",
        description="The finishing cut for Claude Code skills",
        epilog="Quick start:\n"
               "  schliff demo              See it in action instantly\n"
               "  schliff score SKILL.md    Score a skill\n"
               "  schliff doctor            Scan all installed skills",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # score command
    score_parser = subparsers.add_parser("score", help="Score a SKILL.md file")
    score_parser.add_argument("skill_path", nargs="?", help="Path to SKILL.md")
    score_parser.add_argument("--url", help="URL to fetch and score (HTTPS only, allowlisted hosts)")
    score_parser.add_argument("--json", action="store_true", help="JSON output")
    score_parser.add_argument("--eval-suite", help="Path to eval-suite.json")
    score_parser.add_argument(
        "--format",
        choices=["skill.md", "claude.md", "cursorrules", "agents.md", "unknown"],
        default=None,
        help="Override format detection (useful when filename doesn't match content type)",
    )
    score_parser.add_argument("--tokens", action="store_true",
                              help="Show token budget breakdown by section")

    # verify command
    verify_parser = subparsers.add_parser("verify", help="CI gate — exit 0/1 based on score")
    verify_parser.add_argument("skill_path", help="Path to SKILL.md")
    verify_parser.add_argument("--min-score", type=float, default=75.0,
                               help="Minimum passing score (default: 75)")
    verify_parser.add_argument("--regression", action="store_true",
                               help="Fail if score dropped vs previous run")
    verify_parser.add_argument("--history", default=".schliff/history.jsonl",
                               help="Path to history file (default: .schliff/history.jsonl)")
    verify_parser.add_argument("--eval-suite", help="Path to eval-suite.json")
    verify_parser.add_argument("--json", action="store_true", help="JSON output")

    # doctor command
    doctor_parser = subparsers.add_parser("doctor", help="Scan all installed skills")
    doctor_parser.add_argument("--json", action="store_true", help="JSON output")
    doctor_parser.add_argument("--skill-dirs", nargs="+", default=None,
                               help="Directories to scan")
    doctor_parser.add_argument("--verbose", "-v", action="store_true",
                               help="Show per-skill issues")
    doctor_parser.add_argument("--repo", default=None,
                               help="Repository root for instruction file discovery")

    # badge command
    badge_parser = subparsers.add_parser("badge", help="Generate markdown badge for a skill")
    badge_parser.add_argument("skill_path", help="Path to SKILL.md")
    badge_parser.add_argument("--eval-suite", help="Path to eval-suite.json")

    # diff command
    diff_parser = subparsers.add_parser("diff", help="Explain score changes between git commits")
    diff_parser.add_argument("skill_path", help="Path to SKILL.md")
    diff_parser.add_argument("--ref", default="HEAD~1",
                              help="Git ref to compare against (default: HEAD~1)")
    diff_parser.add_argument("--json", action="store_true", help="JSON output")
    diff_parser.add_argument("--eval-suite", help="Path to eval-suite.json")

    # compare command
    compare_parser = subparsers.add_parser("compare", help="Compare two files side by side")
    compare_parser.add_argument("file_a", help="First file to compare")
    compare_parser.add_argument("file_b", help="Second file to compare")
    compare_parser.add_argument("--json", action="store_true", help="JSON output")
    compare_parser.add_argument("--eval-suite", help="Path to eval-suite.json (applied to both)")

    # suggest command
    suggest_parser = subparsers.add_parser("suggest", help="Suggest ranked fixes with estimated impact")
    suggest_parser.add_argument("skill_path", help="Path to SKILL.md")
    suggest_parser.add_argument("--json", action="store_true", help="JSON output")
    suggest_parser.add_argument("--top", type=int, default=5, help="Number of suggestions (default: 5)")
    suggest_parser.add_argument("--eval-suite", help="Path to eval-suite.json")

    # report command
    report_parser = subparsers.add_parser("report", help="Generate Markdown score report")
    report_parser.add_argument("skill_path", help="Path to SKILL.md")
    report_parser.add_argument("--gist", action="store_true",
                               help="Upload report as GitHub Gist (requires GITHUB_TOKEN)")
    report_parser.add_argument("--eval-suite", help="Path to eval-suite.json")

    # demo command
    subparsers.add_parser("demo", help="Score a built-in bad skill to see schliff in action")

    # version command
    subparsers.add_parser("version", help="Show version")

    args = parser.parse_args()

    commands = {
        "score": cmd_score,
        "compare": cmd_compare,
        "diff": cmd_diff,
        "verify": cmd_verify,
        "doctor": cmd_doctor,
        "badge": cmd_badge,
        "suggest": cmd_suggest,
        "report": cmd_report,
        "demo": cmd_demo,
        "version": cmd_version,
    }

    handler = commands.get(args.command)
    if handler:
        handler(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
