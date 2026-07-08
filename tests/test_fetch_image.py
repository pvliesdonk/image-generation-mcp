"""Tests for the fetch_image helper (issue #308)."""

from __future__ import annotations

from image_generation_mcp._fetch_image import _redact_fetch_url


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
