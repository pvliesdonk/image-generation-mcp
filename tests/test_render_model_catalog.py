"""Tests for scripts/render_model_catalog.py."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "render_model_catalog.py"


def _load_renderer():
    spec = importlib.util.spec_from_file_location("render_model_catalog", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["render_model_catalog"] = module
    spec.loader.exec_module(module)
    return module


def test_render_model_catalog_returns_markdown_with_all_provider_sections():
    renderer = _load_renderer()
    output = renderer.render_catalog()
    assert "# Model Catalog" in output
    assert "## OpenAI" in output
    assert "## Gemini" in output
    assert "## Placeholder" in output
    assert "## SD WebUI" in output


def test_render_model_catalog_lists_each_known_model():
    renderer = _load_renderer()
    output = renderer.render_catalog()
    for model_id in (
        "gpt-image-1.5",
        "gpt-image-1",
        "dall-e-3",
        "gemini-2.5-flash-image",
        "placeholder",
    ):
        assert model_id in output, f"missing {model_id} in catalog"


def test_render_model_catalog_lists_all_sd_pattern_labels():
    renderer = _load_renderer()
    output = renderer.render_catalog()
    for label_substring in (
        "FLUX.2",
        "Flux Schnell",
        "Flux 1",
        "Pony",
        "Illustrious",
        "Animagine",
        "Coloring Book",
        "Juggernaut",
        "DreamShaperXL",
        "DreamShaper (versatile SD1.5)",
        "SD 3",
        "SDXL Base",
        "RealVisXL",
        "SD 1.5",
        "Unknown checkpoint",
    ):
        assert label_substring in output, f"missing label {label_substring!r}"


def test_render_writes_to_target_path(tmp_path):
    renderer = _load_renderer()
    target = tmp_path / "model-catalog.md"
    renderer.write_catalog(target)
    assert target.exists()
    text = target.read_text(encoding="utf-8")
    assert "# Model Catalog" in text


def test_committed_catalog_matches_renderer_output():
    """Drift guard — fails CI when registry is edited without regenerating."""
    renderer = _load_renderer()
    expected = renderer.render_catalog()
    committed = (ROOT / "docs" / "providers" / "model-catalog.md").read_text(
        encoding="utf-8"
    )
    assert committed == expected, (
        "docs/providers/model-catalog.md is out of date. "
        "Run `uv run python scripts/render_model_catalog.py` to regenerate."
    )
