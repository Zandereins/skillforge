"""Unit tests for schliff drift detector (drift.py)."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))

import drift as drift_mod


# ---------------------------------------------------------------------------
# extract_references
# ---------------------------------------------------------------------------

class TestExtractReferences:
    """Tests for extract_references()."""

    def test_finds_backtick_paths(self):
        content = "Use `src/main.py` for the entry point."
        refs = drift_mod.extract_references(content)
        assert len(refs) == 1
        assert refs[0]["ref"] == "src/main.py"
        assert refs[0]["type"] == "path"
        assert refs[0]["line"] == 1

    def test_finds_bare_paths_with_extensions(self):
        content = "The config lives at config/settings.yaml in the repo."
        refs = drift_mod.extract_references(content)
        assert any(r["ref"] == "config/settings.yaml" for r in refs)
        assert all(r["type"] == "path" for r in refs)

    def test_finds_npm_run_commands(self):
        content = "Run `npm run build` to compile.\nThen `npm run test:unit`."
        refs = drift_mod.extract_references(content)
        scripts = [r for r in refs if r["type"] == "script"]
        assert len(scripts) == 2
        assert scripts[0]["ref"] == "build"
        assert scripts[1]["ref"] == "test:unit"

    def test_finds_yarn_commands(self):
        content = "Execute `yarn lint` before committing."
        refs = drift_mod.extract_references(content)
        scripts = [r for r in refs if r["type"] == "script"]
        assert len(scripts) == 1
        assert scripts[0]["ref"] == "lint"

    def test_finds_make_targets(self):
        content = "Deploy with `make deploy` and clean with `make clean`."
        refs = drift_mod.extract_references(content)
        targets = [r for r in refs if r["type"] == "make_target"]
        assert len(targets) == 2
        names = {t["ref"] for t in targets}
        assert names == {"deploy", "clean"}

    def test_deduplicates(self):
        content = (
            "See `src/app.ts` for details.\n"
            "Also check `src/app.ts` again.\n"
        )
        refs = drift_mod.extract_references(content)
        paths = [r for r in refs if r["ref"] == "src/app.ts"]
        assert len(paths) == 1, "Duplicate path should be deduplicated"

    def test_empty_content_returns_empty(self):
        refs = drift_mod.extract_references("")
        assert refs == []

    def test_no_refs_in_plain_text(self):
        content = "This is just a plain sentence with no file references."
        refs = drift_mod.extract_references(content)
        assert refs == []

    def test_ignores_urls(self):
        content = "See https://example.com/path/to/file.html for docs."
        refs = drift_mod.extract_references(content)
        urls = [r for r in refs if "example.com" in str(r["ref"])]
        assert len(urls) == 0, "URLs should not be treated as paths"

    def test_line_numbers_are_correct(self):
        content = "line one\n`lib/utils.py` is here\nline three\n`src/index.ts` there"
        refs = drift_mod.extract_references(content)
        by_ref = {r["ref"]: r["line"] for r in refs}
        assert by_ref["lib/utils.py"] == 2
        assert by_ref["src/index.ts"] == 4


# ---------------------------------------------------------------------------
# validate_references
# ---------------------------------------------------------------------------

class TestValidateReferences:
    """Tests for validate_references()."""

    def test_existing_file_marked_valid(self, tmp_path):
        # Create a real file
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("# hello")

        refs = [{"ref": "src/main.py", "type": "path", "line": 1}]
        findings = drift_mod.validate_references(refs, str(tmp_path))

        assert len(findings) == 1
        assert findings[0]["status"] == "valid"

    def test_missing_file_marked_missing(self, tmp_path):
        refs = [{"ref": "src/gone.py", "type": "path", "line": 5}]
        findings = drift_mod.validate_references(refs, str(tmp_path))

        assert len(findings) == 1
        assert findings[0]["status"] == "missing"

    def test_package_json_script_valid(self, tmp_path):
        pkg = {"scripts": {"build": "tsc", "test": "jest"}}
        (tmp_path / "package.json").write_text(json.dumps(pkg))

        refs = [{"ref": "build", "type": "script", "line": 3}]
        findings = drift_mod.validate_references(refs, str(tmp_path))

        assert len(findings) == 1
        assert findings[0]["status"] == "valid"

    def test_package_json_script_missing(self, tmp_path):
        pkg = {"scripts": {"build": "tsc"}}
        (tmp_path / "package.json").write_text(json.dumps(pkg))

        refs = [{"ref": "deploy", "type": "script", "line": 7}]
        findings = drift_mod.validate_references(refs, str(tmp_path))

        assert len(findings) == 1
        assert findings[0]["status"] == "missing"
        assert "not in package.json" in findings[0]["detail"]

    def test_no_package_json_script_missing(self, tmp_path):
        refs = [{"ref": "build", "type": "script", "line": 1}]
        findings = drift_mod.validate_references(refs, str(tmp_path))

        assert len(findings) == 1
        assert findings[0]["status"] == "missing"
        assert "no package.json" in findings[0]["detail"]

    def test_makefile_target_valid(self, tmp_path):
        (tmp_path / "Makefile").write_text("deploy:\n\t@echo deploying\n")

        refs = [{"ref": "deploy", "type": "make_target", "line": 2}]
        findings = drift_mod.validate_references(refs, str(tmp_path))

        assert len(findings) == 1
        assert findings[0]["status"] == "valid"

    def test_makefile_target_missing(self, tmp_path):
        (tmp_path / "Makefile").write_text("build:\n\t@echo building\n")

        refs = [{"ref": "deploy", "type": "make_target", "line": 2}]
        findings = drift_mod.validate_references(refs, str(tmp_path))

        assert len(findings) == 1
        assert findings[0]["status"] == "missing"
        assert "not in Makefile" in findings[0]["detail"]


# ---------------------------------------------------------------------------
# generate_drift_report
# ---------------------------------------------------------------------------

class TestGenerateDriftReport:
    """Tests for generate_drift_report()."""

    def test_empty_findings_returns_empty_string(self):
        assert drift_mod.generate_drift_report([]) == ""

    def test_formats_missing_refs(self):
        findings = [
            {
                "ref": "src/old.py",
                "type": "path",
                "line": 10,
                "status": "missing",
                "detail": "not found: /repo/src/old.py",
            },
        ]
        report = drift_mod.generate_drift_report(findings)
        assert "Missing: 1" in report
        assert "src/old.py" in report
        assert "L10" in report
        assert "[path]" in report

    def test_report_shows_counts(self):
        findings = [
            {"ref": "a/b.py", "type": "path", "line": 1, "status": "valid", "detail": "ok"},
            {"ref": "c/d.py", "type": "path", "line": 2, "status": "missing", "detail": "gone"},
            {"ref": "e/f.py", "type": "path", "line": 3, "status": "valid", "detail": "ok"},
        ]
        report = drift_mod.generate_drift_report(findings)
        assert "References checked: 3" in report
        assert "Missing: 1" in report
        assert "Valid: 2" in report

    def test_report_groups_missing_first(self):
        findings = [
            {"ref": "a/b.py", "type": "path", "line": 1, "status": "valid", "detail": "ok"},
            {"ref": "c/d.py", "type": "path", "line": 2, "status": "missing", "detail": "gone"},
        ]
        report = drift_mod.generate_drift_report(findings)
        missing_pos = report.index("Missing References")
        valid_pos = report.index("Valid References")
        assert missing_pos < valid_pos


# ---------------------------------------------------------------------------
# validate_references — malformed package.json edge case
# ---------------------------------------------------------------------------

class TestPathTraversalPrevention:
    """Ensure path traversal attacks are rejected."""

    def test_dotdot_path_rejected_by_plausible(self):
        """Paths starting with .. are rejected before validation."""
        assert drift_mod._is_plausible_path("../../etc/passwd") is False

    def test_absolute_path_rejected_by_plausible(self):
        """Absolute paths are rejected."""
        assert drift_mod._is_plausible_path("/etc/passwd") is False

    def test_traversal_ref_marked_invalid(self, tmp_path):
        """A ref that escapes repo root is marked invalid, not valid."""
        # Manually craft a ref that bypasses _is_plausible_path
        # (e.g. looks relative but resolves outside)
        refs = [{"ref": "sub/../../outside.py", "type": "path", "line": 1}]
        findings = drift_mod.validate_references(refs, str(tmp_path))
        assert len(findings) == 1
        assert findings[0]["status"] == "invalid"
        assert "escapes repo root" in findings[0]["detail"]

    def test_traversal_does_not_leak_host_paths(self, tmp_path):
        """The detail field must not contain resolved paths outside repo."""
        refs = [{"ref": "sub/../../../etc/passwd", "type": "path", "line": 1}]
        findings = drift_mod.validate_references(refs, str(tmp_path))
        assert len(findings) == 1
        assert "/etc/passwd" not in findings[0].get("detail", "")


class TestValidateReferencesEdgeCases:
    """Edge cases for validate_references with broken project files."""

    def test_malformed_package_json_treats_script_as_missing(self, tmp_path):
        """A malformed package.json should not crash; script is treated as missing."""
        # Write invalid JSON to package.json
        (tmp_path / "package.json").write_text("{not valid json!!!", encoding="utf-8")

        refs = [{"ref": "build", "type": "script", "line": 1}]
        findings = drift_mod.validate_references(refs, str(tmp_path))

        assert len(findings) == 1
        # _load_package_json_scripts catches JSONDecodeError and returns None
        # so the script is reported as missing (package.json unavailable)
        assert findings[0]["status"] == "missing"
        assert "package.json" in findings[0]["detail"]

    def test_empty_package_json_treats_script_as_missing(self, tmp_path):
        """An empty package.json (no scripts key) marks scripts as missing."""
        (tmp_path / "package.json").write_text("{}", encoding="utf-8")

        refs = [{"ref": "test", "type": "script", "line": 5}]
        findings = drift_mod.validate_references(refs, str(tmp_path))

        assert len(findings) == 1
        assert findings[0]["status"] == "missing"
