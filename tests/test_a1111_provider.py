"""Tests for the A1111 (Stable Diffusion WebUI) image provider."""

from __future__ import annotations

import base64
import json
from typing import Any

import httpx
import pytest

from image_gen_mcp.providers.a1111 import (
    _SD15_PRESET,
    _SDXL_LIGHTNING_PRESET,
    _SDXL_PRESET,
    A1111ImageProvider,
    _resolve_preset,
)
from image_gen_mcp.providers.types import (
    ImageProvider,
    ImageProviderConnectionError,
    ImageProviderError,
)


class TestPresetDetection:
    """Tests for _resolve_preset checkpoint detection."""

    def test_no_model_defaults_sd15(self) -> None:
        assert _resolve_preset(None) is _SD15_PRESET

    def test_unknown_model_defaults_sd15(self) -> None:
        assert _resolve_preset("dreamshaper_8") is _SD15_PRESET

    def test_sdxl_model(self) -> None:
        assert _resolve_preset("sdxl_base_1.0") is _SDXL_PRESET

    def test_xl_suffix(self) -> None:
        assert _resolve_preset("juggernaut_xl") is _SDXL_PRESET

    def test_xl_prefix(self) -> None:
        assert _resolve_preset("xl_model") is _SDXL_PRESET

    def test_lightning_sdxl(self) -> None:
        assert _resolve_preset("sdxl_lightning_4step") is _SDXL_LIGHTNING_PRESET

    def test_turbo_sdxl(self) -> None:
        assert _resolve_preset("sdxl_turbo") is _SDXL_LIGHTNING_PRESET

    def test_case_insensitive(self) -> None:
        assert _resolve_preset("SDXL_Base") is _SDXL_PRESET


class TestA1111Provider:
    """Tests for A1111ImageProvider."""

    def test_implements_protocol(self) -> None:
        provider = A1111ImageProvider(host="http://localhost:7860")
        assert isinstance(provider, ImageProvider)

    def test_host_trailing_slash_stripped(self) -> None:
        provider = A1111ImageProvider(host="http://localhost:7860/")
        assert provider._host == "http://localhost:7860"

    def test_model_sets_preset(self) -> None:
        provider = A1111ImageProvider(
            host="http://localhost:7860", model="sdxl_base_1.0"
        )
        assert provider._preset is _SDXL_PRESET

    async def test_generate_success(self, httpx_mock) -> None:
        b64_image = base64.b64encode(b"fake-png-data").decode()
        response_data = {
            "images": [b64_image],
            "info": json.dumps({"seed": 42, "sd_model_name": "dreamshaper_8"}),
        }

        httpx_mock.post(
            "http://localhost:7860/sdapi/v1/txt2img",
            json=response_data,
        )

        provider = A1111ImageProvider(host="http://localhost:7860")
        result = await provider.generate("a cat, masterpiece")

        assert result.image_data == b"fake-png-data"
        assert result.content_type == "image/png"
        assert result.provider_metadata["seed"] == 42
        assert result.provider_metadata["steps"] == 30

    async def test_generate_with_model_override(self, httpx_mock) -> None:
        b64_image = base64.b64encode(b"data").decode()
        response_data = {"images": [b64_image], "info": "{}"}

        httpx_mock.post(
            "http://localhost:7860/sdapi/v1/txt2img",
            json=response_data,
        )

        provider = A1111ImageProvider(
            host="http://localhost:7860", model="sdxl_base_1.0"
        )
        await provider.generate("test")

        request = httpx_mock.get_request()
        payload = json.loads(request.content)
        assert payload["override_settings"]["sd_model_checkpoint"] == "sdxl_base_1.0"
        assert payload["steps"] == 35  # SDXL preset

    async def test_generate_aspect_ratio_maps_to_size(self, httpx_mock) -> None:
        b64_image = base64.b64encode(b"data").decode()
        httpx_mock.post(
            "http://localhost:7860/sdapi/v1/txt2img",
            json={"images": [b64_image], "info": "{}"},
        )

        provider = A1111ImageProvider(host="http://localhost:7860")
        await provider.generate("test", aspect_ratio="16:9")

        request = httpx_mock.get_request()
        payload = json.loads(request.content)
        assert payload["width"] == 1024
        assert payload["height"] == 768

    async def test_generate_negative_prompt(self, httpx_mock) -> None:
        b64_image = base64.b64encode(b"data").decode()
        httpx_mock.post(
            "http://localhost:7860/sdapi/v1/txt2img",
            json={"images": [b64_image], "info": "{}"},
        )

        provider = A1111ImageProvider(host="http://localhost:7860")
        await provider.generate("cat", negative_prompt="blurry, text")

        request = httpx_mock.get_request()
        payload = json.loads(request.content)
        assert payload["negative_prompt"] == "blurry, text"

    async def test_http_error_raises(self, httpx_mock) -> None:
        httpx_mock.post(
            "http://localhost:7860/sdapi/v1/txt2img",
            status_code=500,
            text="Internal Server Error",
        )

        provider = A1111ImageProvider(host="http://localhost:7860")
        with pytest.raises(ImageProviderError, match="HTTP 500"):
            await provider.generate("test")

    async def test_empty_images_raises(self, httpx_mock) -> None:
        httpx_mock.post(
            "http://localhost:7860/sdapi/v1/txt2img",
            json={"images": [], "info": "{}"},
        )

        provider = A1111ImageProvider(host="http://localhost:7860")
        with pytest.raises(ImageProviderError, match="missing 'images'"):
            await provider.generate("test")

    async def test_connection_error(self, monkeypatch) -> None:
        async def _raise_connect(*args: Any, **kwargs: Any) -> None:
            raise httpx.ConnectError("simulated")

        monkeypatch.setattr(httpx.AsyncClient, "post", _raise_connect)
        provider = A1111ImageProvider(host="http://localhost:7860")
        with pytest.raises(ImageProviderConnectionError, match="Cannot connect"):
            await provider.generate("test")


# -- httpx mock fixture -------------------------------------------------------


@pytest.fixture
def httpx_mock(monkeypatch):
    """Simple httpx mock that captures requests and returns canned responses."""
    return _HttpxMock(monkeypatch)


class _HttpxMock:
    """Minimal httpx mock for A1111 tests."""

    def __init__(self, monkeypatch) -> None:
        self._monkeypatch = monkeypatch
        self._routes: list[dict[str, Any]] = []
        self._requests: list[httpx.Request] = []

    def post(
        self,
        url: str,
        *,
        json: dict | None = None,
        status_code: int = 200,
        text: str | None = None,
    ) -> None:
        route = {
            "url": url,
            "json": json,
            "status_code": status_code,
            "text": text,
        }
        self._routes.append(route)
        self._patch()

    def get_request(self) -> httpx.Request:
        assert self._requests, "No requests captured"
        return self._requests[-1]

    def _patch(self) -> None:
        mock = self

        async def _mock_post(
            client_self: Any,  # noqa: ARG001
            url: str,
            **kwargs: Any,
        ) -> httpx.Response:
            # httpx passes json= which gets serialized to content
            json_body = kwargs.get("json")
            content = (
                json.dumps(json_body).encode()
                if json_body is not None
                else kwargs.get("content", b"")
            )
            request = httpx.Request("POST", url, content=content)
            mock._requests.append(request)

            for route in mock._routes:
                if str(url) == route["url"]:
                    if route["text"] is not None:
                        return httpx.Response(
                            status_code=route["status_code"],
                            text=route["text"],
                            request=request,
                        )
                    return httpx.Response(
                        status_code=route["status_code"],
                        json=route["json"],
                        request=request,
                    )

            return httpx.Response(status_code=404, text="Not Found", request=request)

        self._monkeypatch.setattr(httpx.AsyncClient, "post", _mock_post)
