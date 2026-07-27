"""Unit tests for the internalized LSI interpretation module (v6.11.22).

No AI/API call anywhere here by design - these tests pin down the static
band boundaries and dominant-factor selection, which is the whole feature.
"""
from __future__ import annotations

from pooldash_app.lsi_interpretation import interpret_lsi, CORROSIVE_THRESHOLD, SCALING_THRESHOLD


def test_corrosive_band():
    result = interpret_lsi(-0.8)
    assert result.band == "corrosive"
    assert "corrosive" in result.headline.lower() or "etch" in result.description.lower()
    assert len(result.actions) > 0


def test_balanced_band():
    result = interpret_lsi(0.0)
    assert result.band == "balanced"


def test_scaling_band():
    result = interpret_lsi(0.8)
    assert result.band == "scaling"
    assert len(result.actions) > 0


def test_boundary_values_are_balanced_inclusive():
    # -0.3..0.3 is defined as balanced (matches charts.py's chart bands)
    assert interpret_lsi(CORROSIVE_THRESHOLD).band == "balanced"
    assert interpret_lsi(SCALING_THRESHOLD).band == "balanced"


def test_just_past_boundaries():
    assert interpret_lsi(CORROSIVE_THRESHOLD - 0.01).band == "corrosive"
    assert interpret_lsi(SCALING_THRESHOLD + 0.01).band == "scaling"


def test_dominant_factor_picks_largest_magnitude():
    factors = {"A_tds": 0.01, "B_temp": -0.05, "C_calcium": 0.4, "D_alkalinity": -0.02}
    result = interpret_lsi(-0.8, factors=factors)
    assert result.dominant_factor == "calcium hardness"


def test_dominant_factor_none_when_not_provided():
    result = interpret_lsi(-0.8)
    assert result.dominant_factor is None


def test_balanced_band_has_no_dominant_factor():
    factors = {"A_tds": 0.01, "B_temp": -0.05, "C_calcium": 0.4, "D_alkalinity": -0.02}
    result = interpret_lsi(0.0, factors=factors)
    assert result.dominant_factor is None
