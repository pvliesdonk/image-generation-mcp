"""Tests for the info://prompt-guide resource and generate_image description link."""

from __future__ import annotations

import pytest

from image_generation_mcp._server_resources import _PROMPT_GUIDE
from image_generation_mcp.server import make_server


@pytest.fixture
def server(monkeypatch: pytest.MonkeyPatch):
    """Create a read-write server so generate_image is visible."""
    monkeypatch.setenv("IMAGE_GENERATION_MCP_READ_ONLY", "false")
    return make_server()


# -- _PROMPT_GUIDE constant content ------------------------------------------


class TestPromptGuideContent:
    """Verify _PROMPT_GUIDE contains expected per-provider guidance."""

    def test_mentions_openai(self) -> None:
        assert "OpenAI" in _PROMPT_GUIDE

    def test_mentions_gemini(self) -> None:
        assert "Gemini" in _PROMPT_GUIDE

    def test_mentions_sd_webui(self) -> None:
        assert "SD WebUI" in _PROMPT_GUIDE

    def test_mentions_placeholder(self) -> None:
        assert "Placeholder" in _PROMPT_GUIDE

    def test_mentions_clip(self) -> None:
        assert "CLIP" in _PROMPT_GUIDE

    def test_mentions_negative_prompt(self) -> None:
        assert "negative prompt" in _PROMPT_GUIDE.lower()

    def test_mentions_break_syntax(self) -> None:
        assert "BREAK" in _PROMPT_GUIDE

    def test_mentions_avoid_clause_for_openai(self) -> None:
        assert "Avoid:" in _PROMPT_GUIDE

    def test_mentions_token_limits(self) -> None:
        assert "77" in _PROMPT_GUIDE


# -- MCP resource registration -----------------------------------------------


class TestPromptGuideResourceRegistration:
    """Verify info://prompt-guide resource is registered and returns content."""

    async def test_resource_registered(self, server) -> None:
        resources = await server.list_resources()
        uris = [str(r.uri) for r in resources]
        assert "info://prompt-guide" in uris

    async def test_resource_returns_markdown(self, server) -> None:
        result = await server.read_resource("info://prompt-guide")
        assert result.contents[0].mime_type == "text/markdown"
        text = result.contents[0].content
        assert "# Image Generation Prompt Guide" in text

    async def test_resource_available_in_read_only_mode(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """info://prompt-guide must be accessible in read-only mode."""
        monkeypatch.setenv("IMAGE_GENERATION_MCP_READ_ONLY", "true")
        server = make_server()
        resources = await server.list_resources()
        uris = [str(r.uri) for r in resources]
        assert "info://prompt-guide" in uris


# -- generate_image tool description -----------------------------------------


class TestGenerateImageToolDescription:
    """Verify generate_image docstring has inline prompt_style guidance."""

    async def test_generate_image_description_has_prompt_style_guidance(
        self, server
    ) -> None:
        tools = await server.list_tools()
        gen_tool = next(t for t in tools if t.name == "generate_image")
        assert "prompt_style" in gen_tool.description
