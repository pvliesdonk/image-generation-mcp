"""Tests for style library — parsing, scanning, and service integration."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from image_generation_mcp.styles import parse_style, scan_styles

if TYPE_CHECKING:
    from pathlib import Path


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def styles_dir(tmp_path: Path) -> Path:
    """Create a temporary styles directory."""
    d = tmp_path / "styles"
    d.mkdir()
    return d


def _write_style(directory: Path, filename: str, content: str) -> Path:
    """Helper to write a style file."""
    path = directory / filename
    path.write_text(content, encoding="utf-8")
    return path


_VALID_STYLE = """\
---
name: website
tags: [brand, web, modern]
provider: auto
aspect_ratio: "16:9"
quality: hd
---

Minimalist flat illustration. Geometric shapes, clean lines.
Brand palette: deep teal (#0D4F4F), warm cream (#F5F0E8), coral accent (#FF6B5E).
"""

_MINIMAL_STYLE = """\
---
name: minimal
---

Simple and clean.
"""

_NO_FRONTMATTER = """\
Just some markdown without frontmatter.
"""

_MISSING_NAME = """\
---
tags: [test]
---

Body without a name field.
"""

_UNCLOSED_TAG_LIST = """\
---
name: broken
tags: [unclosed
---

Body text.
"""


# ---------------------------------------------------------------------------
# parse_style
# ---------------------------------------------------------------------------


class TestParseStyle:
    def test_valid_frontmatter(self, styles_dir: Path) -> None:
        path = _write_style(styles_dir, "website.md", _VALID_STYLE)
        entry = parse_style(path)
        assert entry is not None
        assert entry.name == "website"
        assert entry.tags == ("brand", "web", "modern")
        assert entry.provider == "auto"
        assert entry.aspect_ratio == "16:9"
        assert entry.quality == "hd"
        assert "Minimalist flat illustration" in entry.body
        assert entry.file_path == path.resolve()

    def test_minimal_frontmatter(self, styles_dir: Path) -> None:
        path = _write_style(styles_dir, "minimal.md", _MINIMAL_STYLE)
        entry = parse_style(path)
        assert entry is not None
        assert entry.name == "minimal"
        assert entry.tags == ()
        assert entry.provider is None
        assert entry.aspect_ratio is None
        assert entry.quality is None
        assert entry.body == "Simple and clean."

    def test_missing_frontmatter(self, styles_dir: Path) -> None:
        path = _write_style(styles_dir, "nofm.md", _NO_FRONTMATTER)
        entry = parse_style(path)
        assert entry is None

    def test_missing_name_field(self, styles_dir: Path) -> None:
        path = _write_style(styles_dir, "noname.md", _MISSING_NAME)
        entry = parse_style(path)
        assert entry is None

    def test_nonexistent_file(self, tmp_path: Path) -> None:
        path = tmp_path / "nonexistent.md"
        entry = parse_style(path)
        assert entry is None

    def test_null_provider(self, styles_dir: Path) -> None:
        content = "---\nname: test\nprovider: null\n---\n\nBody.\n"
        path = _write_style(styles_dir, "test.md", content)
        entry = parse_style(path)
        assert entry is not None
        assert entry.provider is None

    def test_quoted_aspect_ratio(self, styles_dir: Path) -> None:
        content = '---\nname: test\naspect_ratio: "3:2"\n---\n\nBody.\n'
        path = _write_style(styles_dir, "test.md", content)
        entry = parse_style(path)
        assert entry is not None
        assert entry.aspect_ratio == "3:2"

    def test_empty_tags_list(self, styles_dir: Path) -> None:
        content = "---\nname: test\ntags: []\n---\n\nBody.\n"
        path = _write_style(styles_dir, "test.md", content)
        entry = parse_style(path)
        assert entry is not None
        assert entry.tags == ()

    def test_unclosed_tag_list_parsed_as_scalar(self, styles_dir: Path) -> None:
        # An unclosed bracket falls through to the bare-scalar path and
        # is returned as a plain string, which then results in a 1-tuple tag.
        path = _write_style(styles_dir, "broken.md", _UNCLOSED_TAG_LIST)
        entry = parse_style(path)
        # The file has a valid name, so parsing succeeds — tags just gets an
        # unexpected value (treated as a bare string), not None.
        assert entry is not None
        assert entry.name == "broken"

    def test_tags_with_comma_in_quoted_item(self, styles_dir: Path) -> None:
        content = '---\nname: test\ntags: [brand, "web, modern"]\n---\n\nBody.\n'
        path = _write_style(styles_dir, "test.md", content)
        entry = parse_style(path)
        assert entry is not None
        assert entry.tags == ("brand", "web, modern")


# ---------------------------------------------------------------------------
# scan_styles
# ---------------------------------------------------------------------------


class TestScanStyles:
    def test_empty_dir(self, styles_dir: Path) -> None:
        result = scan_styles(styles_dir)
        assert result == {}

    def test_multiple_files(self, styles_dir: Path) -> None:
        _write_style(styles_dir, "website.md", _VALID_STYLE)
        _write_style(styles_dir, "minimal.md", _MINIMAL_STYLE)
        result = scan_styles(styles_dir)
        assert len(result) == 2
        assert "website" in result
        assert "minimal" in result

    def test_non_md_files_ignored(self, styles_dir: Path) -> None:
        _write_style(styles_dir, "website.md", _VALID_STYLE)
        _write_style(styles_dir, "notes.txt", "Not a style file")
        result = scan_styles(styles_dir)
        assert len(result) == 1
        assert "website" in result

    def test_invalid_files_skipped(self, styles_dir: Path) -> None:
        _write_style(styles_dir, "good.md", _VALID_STYLE)
        _write_style(styles_dir, "bad.md", _NO_FRONTMATTER)
        result = scan_styles(styles_dir)
        assert len(result) == 1
        assert "website" in result  # name from _VALID_STYLE

    def test_creates_directory(self, tmp_path: Path) -> None:
        new_dir = tmp_path / "new" / "styles"
        assert not new_dir.exists()
        result = scan_styles(new_dir)
        assert new_dir.exists()
        assert result == {}


# ---------------------------------------------------------------------------
# ImageService style integration
# ---------------------------------------------------------------------------


class TestServiceStyles:
    def test_load_styles(self, tmp_path: Path, styles_dir: Path) -> None:
        from image_generation_mcp.service import ImageService

        _write_style(styles_dir, "website.md", _VALID_STYLE)
        _write_style(styles_dir, "minimal.md", _MINIMAL_STYLE)

        svc = ImageService(scratch_dir=tmp_path / "images")
        svc.load_styles(styles_dir)

        assert len(svc.list_styles()) == 2

    def test_get_style_found(self, tmp_path: Path, styles_dir: Path) -> None:
        from image_generation_mcp.service import ImageService

        _write_style(styles_dir, "website.md", _VALID_STYLE)
        svc = ImageService(scratch_dir=tmp_path / "images")
        svc.load_styles(styles_dir)

        entry = svc.get_style("website")
        assert entry is not None
        assert entry.name == "website"

    def test_get_style_not_found(self, tmp_path: Path) -> None:
        from image_generation_mcp.service import ImageService

        svc = ImageService(scratch_dir=tmp_path / "images")
        assert svc.get_style("nonexistent") is None

    def test_list_styles_ordering(self, tmp_path: Path, styles_dir: Path) -> None:
        from image_generation_mcp.service import ImageService

        _write_style(styles_dir, "website.md", _VALID_STYLE)
        _write_style(styles_dir, "minimal.md", _MINIMAL_STYLE)

        svc = ImageService(scratch_dir=tmp_path / "images")
        svc.load_styles(styles_dir)

        names = [s.name for s in svc.list_styles()]
        assert names == sorted(names)

    def test_save_style_new(self, tmp_path: Path) -> None:
        from image_generation_mcp.service import ImageService

        svc = ImageService(scratch_dir=tmp_path / "images")
        styles_dir = tmp_path / "styles"

        entry = svc.save_style(
            "test-style",
            "A creative brief for testing.",
            styles_dir,
            tags=["test", "demo"],
            provider="openai",
            aspect_ratio="16:9",
            quality="hd",
        )

        assert entry.name == "test-style"
        assert entry.tags == ("test", "demo")
        assert entry.provider == "openai"
        assert entry.aspect_ratio == "16:9"
        assert entry.quality == "hd"
        assert "A creative brief for testing." in entry.body

        # File exists on disk
        assert (styles_dir / "test-style.md").exists()

        # In-memory dict updated
        assert svc.get_style("test-style") is not None

    def test_save_style_overwrites(self, tmp_path: Path) -> None:
        from image_generation_mcp.service import ImageService

        svc = ImageService(scratch_dir=tmp_path / "images")
        styles_dir = tmp_path / "styles"

        svc.save_style("test", "Version 1.", styles_dir)
        svc.save_style("test", "Version 2.", styles_dir)

        entry = svc.get_style("test")
        assert entry is not None
        assert "Version 2." in entry.body

    def test_delete_style(self, tmp_path: Path, styles_dir: Path) -> None:
        from image_generation_mcp.service import ImageService

        _write_style(styles_dir, "website.md", _VALID_STYLE)
        svc = ImageService(scratch_dir=tmp_path / "images")
        svc.load_styles(styles_dir)

        svc.delete_style("website")
        assert svc.get_style("website") is None
        assert not (styles_dir / "website.md").exists()

    def test_delete_style_not_found(self, tmp_path: Path) -> None:
        from image_generation_mcp.service import ImageService

        svc = ImageService(scratch_dir=tmp_path / "images")
        with pytest.raises(KeyError, match="Style not found"):
            svc.delete_style("nonexistent")


# ---------------------------------------------------------------------------
# apply_style prompt
# ---------------------------------------------------------------------------


class TestApplyStylePrompt:
    def test_apply_style_with_valid_style(self, tmp_path: Path) -> None:
        from image_generation_mcp._server_prompts import _build_apply_style_text
        from image_generation_mcp.service import ImageService

        styles_dir = tmp_path / "styles"
        styles_dir.mkdir()
        _write_style(styles_dir, "website.md", _VALID_STYLE)
        svc = ImageService(scratch_dir=tmp_path / "images")
        svc.load_styles(styles_dir)

        entry = svc.get_style("website")
        assert entry is not None

        # We test the text construction directly
        text = _build_apply_style_text(entry, "a hero banner for the homepage")
        assert "website" in text
        assert "hero banner" in text
        assert "Minimalist flat illustration" in text
        assert "Do NOT copy the style text verbatim" in text
        assert "OpenAI" in text
        assert "CLIP" in text

    def test_apply_style_not_found(self, tmp_path: Path) -> None:
        from image_generation_mcp.service import ImageService

        svc = ImageService(scratch_dir=tmp_path / "images")
        result = svc.get_style("nonexistent")
        assert result is None
