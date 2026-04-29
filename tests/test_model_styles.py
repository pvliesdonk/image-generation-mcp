"""Tests for the model_styles registry — schema, resolver, ordering."""

from __future__ import annotations

import dataclasses

import pytest

from image_generation_mcp.providers.model_styles import (
    CHECKPOINT_PATTERNS,
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
    original = MODEL_STYLES.get("openai:dall-e-3")
    MODEL_STYLES["openai:dall-e-3"] = profile
    try:
        result = resolve_style("openai", "dall-e-3")
        assert result is not None
        assert result.label == "ExactHit"
    finally:
        if original is not None:
            MODEL_STYLES["openai:dall-e-3"] = original
        else:
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


def test_all_model_styles_have_non_empty_prose():
    """Every registered profile must carry usable narrative content."""
    assert MODEL_STYLES, "MODEL_STYLES must not be empty"
    for key, profile in MODEL_STYLES.items():
        assert profile.label, f"{key}: empty label"
        assert profile.style_hints.strip(), f"{key}: empty style_hints"
        assert profile.incompatible_styles.strip(), f"{key}: empty incompatible_styles"
        assert profile.good_example.strip(), f"{key}: empty good_example"
        assert profile.bad_example.strip(), f"{key}: empty bad_example"
        if profile.lifecycle != "current":
            assert profile.deprecation_note, (
                f"{key}: lifecycle={profile.lifecycle} requires deprecation_note"
            )


@pytest.mark.parametrize(
    "key,expected_lifecycle",
    [
        ("openai:gpt-image-1.5", "current"),
        ("openai:gpt-image-1", "legacy"),
        ("openai:gpt-image-1-mini", "current"),
        ("openai:dall-e-3", "deprecated"),
        ("openai:dall-e-2", "legacy"),
        ("gemini:gemini-2.5-flash-image", "current"),
        ("gemini:gemini-3.1-flash-image-preview", "current"),
        ("gemini:gemini-3-pro-image-preview", "current"),
        ("placeholder:placeholder", "current"),
    ],
)
def test_known_model_lifecycle(key: str, expected_lifecycle: str):
    assert key in MODEL_STYLES
    assert MODEL_STYLES[key].lifecycle == expected_lifecycle


def test_dall_e_3_has_removal_date():
    profile = MODEL_STYLES["openai:dall-e-3"]
    assert profile.deprecation_note is not None
    assert "2026-05-12" in profile.deprecation_note


def test_resolve_style_picks_up_openai():
    profile = resolve_style("openai", "gpt-image-1.5")
    assert profile is not None
    assert profile.lifecycle == "current"


def test_resolve_style_picks_up_gemini():
    profile = resolve_style("gemini", "gemini-2.5-flash-image")
    assert profile is not None
    assert "Nano Banana" in profile.label


def test_resolve_style_picks_up_placeholder():
    profile = resolve_style("placeholder", "placeholder")
    assert profile is not None
    assert profile.lifecycle == "current"


@pytest.mark.parametrize(
    "model_id,expected_label_substring",
    [
        # FLUX.2 must beat generic flux
        ("flux2_dev_nf4.safetensors", "FLUX.2"),
        # Schnell must beat generic flux
        ("flux1_schnell_nf4.safetensors", "Schnell"),
        # Generic flux1 dev still routes to Flux 1 entry
        ("flux1_dev_nf4.safetensors", "Flux 1"),
        # Pony tag system
        ("ponyDiffusionV6XL.safetensors", "Pony"),
        ("autismMix_confetti.safetensors", "Pony"),
        # Illustrious / NoobAI must beat animagine for Illustrious-Animagine fine-tunes
        ("illustriousJuggernaut_v3.safetensors", "Illustrious"),
        ("noobAI_xl_vpred.safetensors", "Illustrious"),
        # Animagine still wins on plain Animagine names
        ("animagineXL_v3.safetensors", "Animagine"),
        # Coloring book
        ("coloringBook_v1.ckpt", "Coloring"),
        # Juggernaut on its own routes to photorealistic, but Illustrious-prefixed routes elsewhere
        ("juggernautXL_v9.safetensors", "Juggernaut"),
        # DreamShaper Lightning specificity
        ("dreamshaperXL_v21Lightning.safetensors", "Lightning"),
        ("dreamshaperXL_v2.safetensors", "DreamShaperXL"),
        ("dreamshaper_8.safetensors", "DreamShaper"),
        # SD3 / SD3.5
        ("sd3_5_large.safetensors", "SD 3"),
        ("sd_3_medium.safetensors", "SD 3"),
        # SDXL base
        ("sd_xl_base_1.0.safetensors", "SDXL Base"),
        # RealVisXL
        ("realvisxl_v4.safetensors", "RealVisXL"),
        # SD 1.5 base
        ("v1-5-pruned-emaonly.safetensors", "SD 1.5"),
        ("sd_1_5_base.safetensors", "SD 1.5"),
        # Default fallback
        ("xyzUnknownCheckpoint.safetensors", "Unknown"),
    ],
)
def test_checkpoint_pattern_routing(model_id: str, expected_label_substring: str):
    profile = resolve_style("sd_webui", model_id)
    assert profile is not None
    assert expected_label_substring in profile.label, (
        f"{model_id} routed to {profile.label!r}, expected substring "
        f"{expected_label_substring!r}"
    )


def test_default_fallback_is_last_pattern():
    """Empty-pattern entry must be the final tuple element."""
    last_pattern, _ = CHECKPOINT_PATTERNS[-1]
    assert last_pattern.pattern == ""
    # Sanity: every other pattern is non-empty
    for pattern, _ in CHECKPOINT_PATTERNS[:-1]:
        assert pattern.pattern, "non-default fallback patterns must be non-empty"
