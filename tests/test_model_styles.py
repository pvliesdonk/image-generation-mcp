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


from image_generation_mcp.providers.model_styles import resolve_style  # noqa: E402


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
