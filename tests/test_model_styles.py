"""Tests for the model_styles registry — schema, resolver, ordering."""

from __future__ import annotations

import dataclasses

import pytest

from image_generation_mcp.providers.model_styles import StyleProfile


def test_style_profile_to_dict_omits_deprecation_note_when_none():
    profile = StyleProfile(
        label="Test",
        style_hints="hints",
        incompatible_styles="bad",
        good_example="good",
        bad_example="bad",
    )
    result = profile.to_dict()
    assert "deprecation_note" not in result
    assert result["lifecycle"] == "current"
    assert result["label"] == "Test"


def test_style_profile_to_dict_includes_deprecation_note():
    profile = StyleProfile(
        label="Old",
        style_hints="h",
        incompatible_styles="b",
        good_example="g",
        bad_example="bx",
        lifecycle="deprecated",
        deprecation_note="API removal 2026-05-12.",
    )
    result = profile.to_dict()
    assert result["deprecation_note"] == "API removal 2026-05-12."
    assert result["lifecycle"] == "deprecated"


def test_style_profile_is_frozen():
    profile = StyleProfile(
        label="x",
        style_hints="x",
        incompatible_styles="x",
        good_example="x",
        bad_example="x",
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        profile.label = "y"  # type: ignore[misc]
