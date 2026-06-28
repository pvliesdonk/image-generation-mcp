"""Pytest configuration and shared fixtures."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
from fastmcp import Client

from image_generation_mcp.server import make_server

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Generator
    from pathlib import Path
    from typing import Any

    from image_generation_mcp.providers.gemini import GeminiImageProvider


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove all IMAGE_GENERATION_MCP_* env vars before each test.

    Prevents env var leakage between tests that call :func:`make_server`.
    """
    import os

    for key in list(os.environ):
        if key.startswith("IMAGE_GENERATION_MCP_"):
            monkeypatch.delenv(key, raising=False)


@pytest.fixture
async def client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[Client[Any]]:
    """In-memory FastMCP client connected to a fresh ``make_server()``.

    Template-conformant smoke fixture: the lifespan runs on connect, so the
    yielded client exercises the wired server (tools / resources / prompts and
    the started service). Scratch/styles dirs are pointed at ``tmp_path`` so the
    lifespan's style-library load (and any image writes) never touch the user's
    home directory.
    """
    monkeypatch.setenv("IMAGE_GENERATION_MCP_SCRATCH_DIR", str(tmp_path / "images"))
    monkeypatch.setenv("IMAGE_GENERATION_MCP_STYLES_DIR", str(tmp_path / "styles"))
    async with Client(make_server()) as c:
        yield c


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
