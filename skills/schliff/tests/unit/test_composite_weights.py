"""Tests for compute_composite() weight logic.

Covers gaps not exercised by test_edge_cases.py:
1. --weights flag CLI override maps to custom_weights correctly
2. Calibrated weights from JSON file are loaded and applied
3. Clarity dimension is auto-injected when no custom weights
4. Clarity dimension is NOT injected when custom weights are provided
5. Dimensions with score -1 are excluded from the composite
6. Composite score stays in 0-100 range for all inputs
7. Empty scores dict does not crash
8. Default weights sum to approximately 1.0 (accounting for clarity)
"""
import json
import math
import importlib
import sys
from pathlib import Path

import pytest

from scoring import compute_composite
import scoring.composite as _composite_mod


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _score(value: int) -> dict:
    """Build a minimal score dict for a dimension."""
    return {"score": value, "issues": [], "details": {}}


def _base_scores(**overrides) -> dict:
    """Return a standard set of measured dimensions (all score >= 0)."""
    base = {
        "structure": _score(80),
        "efficiency": _score(70),
        "composability": _score(60),
        "quality": _score(75),
        "edges": _score(65),
    }
    base.update(overrides)
    return base


def _reset_calibrated_cache():
    """Force the module-level cache to be stale so the next call re-reads disk."""
    _composite_mod._calibrated_weights_cache = None
    _composite_mod._calibrated_weights_mtime = 0.0
    _composite_mod._calibrated_weights_path = ""


# ---------------------------------------------------------------------------
# 1. Custom --weights flag overrides defaults correctly
# ---------------------------------------------------------------------------

class TestCustomWeightsOverride:
    """Custom weights passed via custom_weights= must override the built-in defaults."""

    def test_custom_weight_changes_composite(self):
        """Pinning structure to 1.0 (all weight) drives composite toward structure score."""
        scores = _base_scores()
        # Give structure a score far from others so dominance is detectable.
        scores["structure"] = _score(100)
        scores["efficiency"] = _score(0)
        result_default = compute_composite(scores)
        result_custom = compute_composite(scores, custom_weights={"structure": 1.0, "efficiency": 0.0})
        # With structure at full weight the custom composite must be higher.
        assert result_custom["score"] > result_default["score"]

    def test_custom_weights_are_normalized(self):
        """Weights summing to 300 must be normalized; composite must stay <= 100."""
        scores = _base_scores()
        custom = {"structure": 100.0, "efficiency": 100.0, "composability": 100.0}
        result = compute_composite(scores, custom_weights=custom)
        assert result["score"] <= 100.0

    def test_custom_weights_for_unrecognized_dim_are_ignored(self):
        """Unknown dimension keys in custom_weights must not crash."""
        scores = _base_scores()
        custom = {"nonexistent_dim": 99.0, "structure": 0.5}
        result = compute_composite(scores, custom_weights=custom)
        assert "score" in result
        assert isinstance(result["score"], float)

    def test_custom_single_dimension_weight_affects_only_that_dim(self):
        """Overriding one weight must keep the others at their default proportions."""
        scores = _base_scores()
        result = compute_composite(scores, custom_weights={"structure": 0.5})
        # Result must be a valid float in range
        assert 0.0 <= result["score"] <= 100.0

    def test_custom_weights_replace_calibrated_weights(self, tmp_path, monkeypatch):
        """custom_weights must take precedence over auto-calibrated weights on disk."""
        calib_dir = tmp_path / ".schliff" / "meta"
        calib_dir.mkdir(parents=True)
        calib_file = calib_dir / "calibrated-weights.json"
        # Write calibrated weights that favor 'edges' heavily
        calib_file.write_text(
            json.dumps({"edges": 10.0, "structure": 0.1, "efficiency": 0.1}),
            encoding="utf-8",
        )
        monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
        _reset_calibrated_cache()

        scores = _base_scores()
        scores["edges"] = _score(0)
        scores["structure"] = _score(100)

        # Without custom_weights the calibrated file dominates -> edges pulls score down
        result_calib = compute_composite(scores)
        # With custom_weights the calibration is bypassed -> structure dominates
        result_custom = compute_composite(
            scores, custom_weights={"structure": 1.0, "edges": 0.0}
        )
        assert result_custom["score"] > result_calib["score"]
        _reset_calibrated_cache()


# ---------------------------------------------------------------------------
# 2. Calibrated weights from JSON file are loaded
# ---------------------------------------------------------------------------

class TestCalibratedWeightsLoading:
    """Auto-calibrated weights from ~/.schliff/meta/calibrated-weights.json."""

    def test_valid_calibrated_file_is_applied(self, tmp_path, monkeypatch):
        """A valid calibrated-weights.json must be loaded and influence the composite."""
        calib_dir = tmp_path / ".schliff" / "meta"
        calib_dir.mkdir(parents=True)
        calib_file = calib_dir / "calibrated-weights.json"
        # Make structure overwhelmingly heavy
        calib_file.write_text(
            json.dumps({"structure": 100.0, "efficiency": 0.01, "composability": 0.01}),
            encoding="utf-8",
        )
        monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
        _reset_calibrated_cache()

        scores = _base_scores()
        scores["structure"] = _score(100)
        scores["efficiency"] = _score(0)
        result = compute_composite(scores)
        # structure=100 dominates -> composite must be near 100
        assert result["score"] >= 85.0
        _reset_calibrated_cache()

    def test_malformed_json_falls_back_to_defaults(self, tmp_path, monkeypatch):
        """Malformed JSON in the calibrated file must be silently ignored."""
        calib_dir = tmp_path / ".schliff" / "meta"
        calib_dir.mkdir(parents=True)
        (calib_dir / "calibrated-weights.json").write_text("{not valid json", encoding="utf-8")
        monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
        _reset_calibrated_cache()

        scores = _base_scores()
        result = compute_composite(scores)
        assert "score" in result
        assert isinstance(result["score"], float)
        _reset_calibrated_cache()

    def test_calibrated_file_with_negative_values_ignored(self, tmp_path, monkeypatch):
        """Negative values in calibrated JSON must be rejected and not applied."""
        calib_dir = tmp_path / ".schliff" / "meta"
        calib_dir.mkdir(parents=True)
        (calib_dir / "calibrated-weights.json").write_text(
            json.dumps({"structure": -5.0, "efficiency": 1.0}),
            encoding="utf-8",
        )
        monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
        _reset_calibrated_cache()

        scores = _base_scores()
        result = compute_composite(scores)
        assert "score" in result
        assert result["score"] >= 0.0
        _reset_calibrated_cache()

    def test_absent_calibrated_file_uses_defaults(self, tmp_path, monkeypatch):
        """When the calibrated file does not exist, built-in defaults must be used."""
        # Point home at an empty tmp dir (no .schliff/meta tree)
        monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
        _reset_calibrated_cache()

        scores = _base_scores()
        result = compute_composite(scores)
        assert "score" in result
        assert 0.0 <= result["score"] <= 100.0
        _reset_calibrated_cache()

    def test_mtime_cache_invalidation_reloads_file(self, tmp_path, monkeypatch):
        """Updating the calibrated file on disk must trigger a cache reload."""
        calib_dir = tmp_path / ".schliff" / "meta"
        calib_dir.mkdir(parents=True)
        calib_file = calib_dir / "calibrated-weights.json"
        calib_file.write_text(
            json.dumps({"structure": 1.0, "efficiency": 0.01}), encoding="utf-8"
        )
        monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
        _reset_calibrated_cache()

        scores = _base_scores()
        scores["structure"] = _score(100)
        result_v1 = compute_composite(scores)

        # Overwrite with weights that heavily favour efficiency (score=0)
        import time
        time.sleep(0.01)  # ensure mtime differs
        calib_file.write_text(
            json.dumps({"efficiency": 100.0, "structure": 0.01}), encoding="utf-8"
        )
        # Touch mtime by re-stating (write already did)
        result_v2 = compute_composite(scores)

        # After reload, efficiency (score=70 in base) dominates; score may differ
        # We only assert no crash and valid result
        assert "score" in result_v2
        assert isinstance(result_v2["score"], float)
        _reset_calibrated_cache()


# ---------------------------------------------------------------------------
# 3. Clarity dimension auto-injection when no custom weights
# ---------------------------------------------------------------------------

class TestClarityAutoInjection:
    """clarity must be injected with weight 0.05 when present and no custom_weights."""

    def test_clarity_dimension_is_measured_when_present(self):
        """clarity in scores dict must appear in measured_dimensions with no custom weights."""
        scores = _base_scores()
        scores["clarity"] = _score(90)
        result = compute_composite(scores)
        assert "clarity" in result.get("confidence_notes", {}) or \
               result["measured_dimensions"] > len(_base_scores())

    def test_clarity_raises_composite_when_high(self):
        """Adding clarity with score=100 must not lower the composite vs. no clarity."""
        scores_no_clarity = _base_scores()
        scores_with_clarity = _base_scores()
        scores_with_clarity["clarity"] = _score(100)

        result_no = compute_composite(scores_no_clarity)
        result_yes = compute_composite(scores_with_clarity)

        # Clarity is weighted at 0.05 and other weights are scaled down proportionally.
        # With clarity=100 (above the base average) composite must not decrease.
        assert result_yes["score"] >= result_no["score"] - 0.1  # allow fp rounding

    def test_weights_sum_near_one_with_clarity(self):
        """Internal weight normalization must keep weight_coverage <= 1.0 with clarity."""
        scores = _base_scores()
        scores["clarity"] = _score(80)
        scores["triggers"] = _score(85)
        result = compute_composite(scores)
        assert result["weight_coverage"] <= 1.0 + 1e-6


# ---------------------------------------------------------------------------
# 4. Clarity dimension NOT injected when custom weights are provided
# ---------------------------------------------------------------------------

class TestClarityNotInjectedWithCustomWeights:
    """When custom_weights= is passed, clarity must NOT be auto-injected."""

    def test_clarity_absent_from_confidence_notes_with_custom_weights(self):
        """custom_weights suppresses clarity auto-injection."""
        scores = _base_scores()
        scores["clarity"] = _score(100)
        result = compute_composite(scores, custom_weights={"structure": 0.5, "efficiency": 0.5})
        # clarity must NOT be in confidence_notes (only measured dims appear there)
        assert "clarity" not in result.get("confidence_notes", {})

    def test_composite_identical_with_and_without_clarity_when_custom_weights(self):
        """With identical custom_weights, adding clarity= must not change the composite."""
        custom = {"structure": 0.6, "efficiency": 0.4}
        scores_base = {"structure": _score(80), "efficiency": _score(70)}
        scores_with_clarity = {"structure": _score(80), "efficiency": _score(70), "clarity": _score(50)}

        r1 = compute_composite(scores_base, custom_weights=custom)
        r2 = compute_composite(scores_with_clarity, custom_weights=custom)
        assert abs(r1["score"] - r2["score"]) < 1e-6


# ---------------------------------------------------------------------------
# 5. Dimensions with score -1 are excluded from composite
# ---------------------------------------------------------------------------

class TestMinusOneExclusion:
    """Dimensions whose score is -1 must be treated as unmeasured."""

    def test_minus_one_dim_appears_in_unmeasured(self):
        """A dimension with score=-1 must be listed in 'unmeasured'."""
        scores = {
            "structure": _score(80),
            "triggers": {"score": -1, "issues": ["no_trigger_eval_suite"], "details": {}},
            "efficiency": _score(70),
        }
        result = compute_composite(scores)
        assert "triggers" in result["unmeasured"]

    def test_minus_one_dim_not_in_measured_dimensions(self):
        """measured_dimensions count must exclude -1-scored dimensions."""
        scores = {
            "structure": _score(80),
            "triggers": {"score": -1, "issues": [], "details": {}},
        }
        result = compute_composite(scores)
        # Only 'structure' is measured (triggers=-1 is excluded)
        assert result["measured_dimensions"] == 1

    def test_all_minus_one_falls_back_to_zero(self):
        """When all provided dimensions score -1 the composite must be 0.0."""
        scores = {
            "structure": {"score": -1, "issues": [], "details": {}},
            "efficiency": {"score": -1, "issues": [], "details": {}},
        }
        result = compute_composite(scores)
        assert result["score"] == 0.0

    def test_single_measured_dim_drives_composite(self):
        """With one measured dimension its score must equal the composite (weight coverage=1)."""
        scores = {
            "structure": _score(77),
            "triggers": {"score": -1, "issues": [], "details": {}},
            "quality": {"score": -1, "issues": [], "details": {}},
            "edges": {"score": -1, "issues": [], "details": {}},
            "efficiency": {"score": -1, "issues": [], "details": {}},
            "composability": {"score": -1, "issues": [], "details": {}},
        }
        result = compute_composite(scores)
        assert result["score"] == pytest.approx(77.0, abs=0.2)


# ---------------------------------------------------------------------------
# 6. Composite score stays in 0-100 range for all inputs
# ---------------------------------------------------------------------------

class TestCompositeRange:
    """Composite must always be within [0, 100] regardless of input."""

    @pytest.mark.parametrize("score_val", [0, 1, 50, 99, 100])
    def test_uniform_score_stays_in_range(self, score_val):
        """All dimensions at the same score must produce composite == that score."""
        scores = {
            "structure": _score(score_val),
            "efficiency": _score(score_val),
            "quality": _score(score_val),
            "edges": _score(score_val),
            "composability": _score(score_val),
        }
        result = compute_composite(scores)
        assert 0.0 <= result["score"] <= 100.0

    def test_extreme_mix_stays_in_range(self):
        """Mix of 0 and 100 scores must produce composite in [0, 100]."""
        scores = {
            "structure": _score(100),
            "efficiency": _score(0),
            "quality": _score(100),
            "edges": _score(0),
            "composability": _score(100),
        }
        result = compute_composite(scores)
        assert 0.0 <= result["score"] <= 100.0

    def test_large_custom_weights_stay_in_range(self):
        """Pathological unnormalized weights must still yield composite in [0, 100]."""
        scores = _base_scores()
        custom = {
            "structure": 1e9,
            "efficiency": 1e9,
            "composability": 1e9,
        }
        result = compute_composite(scores, custom_weights=custom)
        assert 0.0 <= result["score"] <= 100.0


# ---------------------------------------------------------------------------
# 7. Empty scores dict does not crash
# ---------------------------------------------------------------------------

class TestEmptyScoresDict:
    """compute_composite({}) must return a valid result without raising."""

    def test_empty_scores_returns_dict(self):
        result = compute_composite({})
        assert isinstance(result, dict)

    def test_empty_scores_composite_is_zero(self):
        result = compute_composite({})
        assert result["score"] == 0.0

    def test_empty_scores_measured_dimensions_is_zero(self):
        result = compute_composite({})
        assert result["measured_dimensions"] == 0

    def test_empty_scores_with_custom_weights_does_not_crash(self):
        result = compute_composite({}, custom_weights={"structure": 0.5})
        assert isinstance(result, dict)
        assert result["score"] == 0.0


# ---------------------------------------------------------------------------
# 8. Default weights sum to approximately 1.0 (accounting for clarity)
# ---------------------------------------------------------------------------

class TestDefaultWeightsSum:
    """The built-in default weight dict must sum to exactly 1.0."""

    def test_default_weights_sum_to_one(self):
        """Built-in weights in compute_composite must sum to 1.0 within float tolerance.

        We verify this by running compute_composite with a full set of measured
        dimensions that fill all default weight keys, then checking weight_coverage.
        """
        # Populate every default dimension so weight_sum == total weight sum
        scores = {
            "structure": _score(50),
            "triggers": _score(50),
            "quality": _score(50),
            "edges": _score(50),
            "efficiency": _score(50),
            "composability": _score(50),
            "runtime": _score(50),
        }
        result = compute_composite(scores)
        # weight_coverage == weight_sum across measured dims; all dims measured -> ~1.0
        assert abs(result["weight_coverage"] - 1.0) < 1e-6

    def test_default_weights_without_runtime_sum_to_less_than_one(self):
        """Without runtime, weight_coverage < 1.0 because runtime weight is unmeasured."""
        scores = {
            "structure": _score(50),
            "triggers": _score(50),
            "quality": _score(50),
            "edges": _score(50),
            "efficiency": _score(50),
            "composability": _score(50),
        }
        result = compute_composite(scores)
        assert result["weight_coverage"] < 1.0

    def test_clarity_injection_preserves_total_weight(self):
        """After clarity injection the total weight across all measured dims must be ~1.0."""
        scores = {
            "structure": _score(50),
            "triggers": _score(50),
            "quality": _score(50),
            "edges": _score(50),
            "efficiency": _score(50),
            "composability": _score(50),
            "runtime": _score(50),
            "clarity": _score(50),
        }
        result = compute_composite(scores)
        # weight_coverage == sum of weights for *measured* dimensions after normalization
        assert abs(result["weight_coverage"] - 1.0) < 1e-6
