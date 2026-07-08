"""Tests for the fetch_image helper (issue #308)."""

from __future__ import annotations

import io

import httpx
import pytest
from PIL import Image

from image_generation_mcp._fetch_image import (
    _redact_fetch_url,
    fetch_image_into_gallery,
)
from image_generation_mcp._input_images import InvalidInputImage
from image_generation_mcp.domain import ImageService


def _png_bytes(color: str = "red") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), color).save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def service(tmp_path) -> ImageService:
    return ImageService(scratch_dir=tmp_path)


def _png_transport(status: int = 200, body: bytes | None = None) -> httpx.MockTransport:
    payload = _png_bytes() if body is None else body

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status, content=payload, headers={"content-type": "image/png"}
        )

    return httpx.MockTransport(handler)


# A public IP literal skips DNS (hermetic); MockTransport handles the dial.
_PUBLIC_URL = "http://93.184.216.34/img.png"


async def test_fetch_success_registers_imported(service: ImageService) -> None:
    record = await fetch_image_into_gallery(
        service,
        _PUBLIC_URL,
        max_bytes=1_000_000,
        timeout_s=5,
        transport=_png_transport(),
    )
    assert record.origin == "imported"
    assert record.origin_source == "fetch:http://93.184.216.34/img.png"


async def test_fetch_redacts_secret_in_provenance(service: ImageService) -> None:
    url = "http://user:pass@93.184.216.34/img.png?token=SECRET"
    record = await fetch_image_into_gallery(
        service, url, max_bytes=1_000_000, timeout_s=5, transport=_png_transport()
    )
    assert record.origin_source is not None
    assert "SECRET" not in record.origin_source
    assert "pass" not in record.origin_source
    assert record.origin_source == "fetch:http://93.184.216.34/img.png"


async def test_fetch_ssrf_blocked_raises_valueerror(service: ImageService) -> None:
    # Link-local literal: rejected pre-connect, no transport needed.
    with pytest.raises(ValueError, match="private, loopback"):
        await fetch_image_into_gallery(
            service, "http://169.254.169.254/meta", max_bytes=1000, timeout_s=5
        )


async def test_fetch_non_2xx_raises_status_error(service: ImageService) -> None:
    with pytest.raises(httpx.HTTPStatusError):
        await fetch_image_into_gallery(
            service,
            _PUBLIC_URL,
            max_bytes=1_000_000,
            timeout_s=5,
            transport=_png_transport(status=404),
        )


async def test_fetch_oversized_raises_valueerror(service: ImageService) -> None:
    with pytest.raises(ValueError):
        await fetch_image_into_gallery(
            service, _PUBLIC_URL, max_bytes=10, timeout_s=5, transport=_png_transport()
        )


async def test_fetch_timeout_raises_transport_error(service: ImageService) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out", request=request)

    with pytest.raises(httpx.TransportError):
        await fetch_image_into_gallery(
            service,
            _PUBLIC_URL,
            max_bytes=1_000_000,
            timeout_s=5,
            transport=httpx.MockTransport(handler),
        )


async def test_fetch_non_image_raises_invalid(service: ImageService) -> None:
    with pytest.raises(InvalidInputImage):
        await fetch_image_into_gallery(
            service,
            _PUBLIC_URL,
            max_bytes=1_000_000,
            timeout_s=5,
            transport=_png_transport(body=b"not an image"),
        )


def test_redact_drops_userinfo_query_fragment() -> None:
    url = "https://user:pass@example.com/dir/img.png?token=SECRET#frag"
    assert _redact_fetch_url(url) == "https://example.com/dir/img.png"


def test_redact_keeps_explicit_port() -> None:
    assert _redact_fetch_url("http://host:8080/a?x=1") == "http://host:8080/a"


def test_redact_brackets_ipv6_host() -> None:
    assert (
        _redact_fetch_url("http://[2001:db8::1]:443/p?q=1")
        == "http://[2001:db8::1]:443/p"
    )
