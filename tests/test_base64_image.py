"""Tests for the base64 ingest helper (issue #309)."""

from __future__ import annotations

from image_generation_mcp._base64_image import _normalize_base64


def test_normalize_strips_data_uri_prefix() -> None:
    assert _normalize_base64("data:image/png;base64,aGVsbG8=") == "aGVsbG8="


def test_normalize_strips_whitespace_and_newlines() -> None:
    assert _normalize_base64("aGVs\n bG8=\r\n") == "aGVsbG8="


def test_normalize_leaves_raw_base64_unchanged() -> None:
    assert _normalize_base64("aGVsbG8=") == "aGVsbG8="
