"""Pytest configuration and shared fixtures."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

if TYPE_CHECKING:
    from collections.abc import Generator

    from image_generation_mcp.providers.gemini import GeminiImageProvider


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove all IMAGE_GENERATION_MCP_* env vars before each test.

    Prevents env var leakage between tests that call :func:`create_server`.
    """
    import os

    for key in list(os.environ):
        if key.startswith("IMAGE_GENERATION_MCP_"):
            monkeypatch.delenv(key, raising=False)


@pytest.fixture
def _mock_genai() -> Generator[None, None, None]:
    """Patch google-genai imports so tests don't need the real package installed."""
    mock_types = MagicMock()
    mock_genai = MagicMock()
    mock_genai.types = mock_types
    mock_google = MagicMock()
    mock_google.genai = mock_genai

    modules = {
        "google": mock_google,
        "google.genai": mock_genai,
        "google.genai.types": mock_types,
    }

    with (
        patch.dict(sys.modules, modules),
        patch(
            "image_generation_mcp.providers.gemini.GeminiImageProvider._create_client"
        ),
    ):
        yield


@pytest.fixture
def gemini_provider(_mock_genai: None) -> GeminiImageProvider:
    """GeminiImageProvider with google-genai patched out."""
    from image_generation_mcp.providers.gemini import GeminiImageProvider

    return GeminiImageProvider(api_key="AIza-test")
