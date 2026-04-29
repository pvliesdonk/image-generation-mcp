"""Tests for the model_styles registry — schema, resolver, ordering."""

from __future__ import annotations

import dataclasses

import pytest

from image_generation_mcp.providers.model_styles import (
    MODEL_STYLES,
    StyleProfile,
    resolve_style,
)


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


def test_resolve_style_returns_none_for_unknown_provider():
    assert resolve_style("future-provider", "any-model") is None


def test_resolve_style_returns_none_for_openai_unknown_model():
    assert resolve_style("openai", "definitely-not-a-real-model-id") is None


def test_resolve_style_sd_webui_falls_back_to_default():
    profile = resolve_style(
        "sd_webui", "completely-unknown-checkpoint-xyz123.safetensors"
    )
    assert profile is not None
    assert "Unknown checkpoint" in profile.label


def test_resolve_style_sd_webui_is_case_insensitive():
    profile = resolve_style("sd_webui", "TOTALLY-RANDOM-NAME")
    assert profile is not None  # default fallback always matches


def test_resolve_style_exact_key_hit_in_model_styles():
    """resolve_style returns the registered profile for an exact-key match."""
    profile = StyleProfile(
        label="ExactHit",
        style_hints="s",
        incompatible_styles="i",
        good_example="g",
        bad_example="b",
    )
    MODEL_STYLES["openai:dall-e-3"] = profile
    try:
        result = resolve_style("openai", "dall-e-3")
        assert result is not None
        assert result.label == "ExactHit"
    finally:
        del MODEL_STYLES["openai:dall-e-3"]


def test_style_profile_legacy_lifecycle_omits_deprecation_note():
    """A legacy-lifecycle profile without a deprecation_note still serialises cleanly."""
    profile = StyleProfile(
        label="L",
        style_hints="h",
        incompatible_styles="i",
        good_example="g",
        bad_example="b",
        lifecycle="legacy",
    )
    result = profile.to_dict()
    assert result["lifecycle"] == "legacy"
    assert "deprecation_note" not in result
