"""Style library — parse and scan markdown style files with YAML frontmatter.

Styles are creative briefs stored as ``.md`` files in a configurable directory.
Each file has YAML frontmatter (name, tags, provider, aspect_ratio, quality)
and a markdown prose body that the LLM interprets per-provider.

See ADR-0008 for the design rationale.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path  # noqa: TC003 — used at runtime
from typing import Any

logger = logging.getLogger(__name__)

# Regex to split YAML frontmatter from body.
# Matches files starting with "---\n", then captures everything up to the
# next "\n---\n" (or "\n---" at EOF), with the remainder as body.
_FRONTMATTER_RE = re.compile(
    r"\A---[ \t]*\r?\n(.*?\r?\n)---[ \t]*\r?\n?(.*)\Z",
    re.DOTALL,
)


@dataclass(frozen=True)
class StyleEntry:
    """A parsed style definition.

    Attributes:
        name: Style identifier (matches filename without ``.md``).
        tags: Categorization tags for filtering/browsing.
        provider: Suggested provider (``"auto"`` or a specific name).
        aspect_ratio: Default aspect ratio (e.g. ``"16:9"``), or ``None``.
        quality: Default quality level (``"standard"`` or ``"hd"``), or ``None``.
        body: Markdown prose after frontmatter — the creative brief.
        file_path: Absolute path to the source ``.md`` file.
    """

    name: str
    tags: tuple[str, ...]
    provider: str | None
    aspect_ratio: str | None
    quality: str | None
    body: str
    file_path: Path


def _parse_yaml_value(raw: str) -> Any:
    """Parse a single YAML scalar or inline list value.

    Handles:
    - Inline lists: ``[a, b, c]``
    - Quoted strings: ``"16:9"`` or ``'16:9'``
    - Bare scalars: ``auto``, ``hd``, ``null``

    Args:
        raw: Raw YAML value string (already stripped of key prefix).

    Returns:
        Parsed Python value.
    """
    raw = raw.strip()

    # null / empty
    if not raw or raw in ("null", "~"):
        return None

    # Inline list: [a, b, c]
    if raw.startswith("[") and raw.endswith("]"):
        inner = raw[1:-1]
        if not inner.strip():
            return []
        items = []
        for item in inner.split(","):
            item = item.strip()
            # Strip quotes from list items
            if len(item) >= 2 and item[0] == item[-1] and item[0] in ('"', "'"):
                item = item[1:-1]
            if item:
                items.append(item)
        return items

    # Quoted string
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in ('"', "'"):
        return raw[1:-1]

    return raw


def _parse_frontmatter(text: str) -> dict[str, Any]:
    """Parse simple YAML frontmatter into a dict.

    Only supports flat key-value pairs (no nesting beyond inline lists).

    Args:
        text: The YAML text between the ``---`` delimiters.

    Returns:
        Dict of parsed key-value pairs.
    """
    result: dict[str, Any] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        colon_idx = line.find(":")
        if colon_idx < 1:
            continue
        key = line[:colon_idx].strip()
        value = line[colon_idx + 1 :].strip()
        result[key] = _parse_yaml_value(value)
    return result


def parse_style(path: Path) -> StyleEntry | None:
    """Read a markdown style file and parse its YAML frontmatter.

    Args:
        path: Path to a ``.md`` style file.

    Returns:
        A :class:`StyleEntry` if parsing succeeds, or ``None`` if the file
        is missing frontmatter, has invalid YAML, or lacks a ``name`` field.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        logger.warning("Cannot read style file: %s", path)
        return None

    match = _FRONTMATTER_RE.match(text)
    if not match:
        logger.warning("Style file missing frontmatter: %s", path)
        return None

    frontmatter_text, body = match.group(1), match.group(2)

    try:
        fm = _parse_frontmatter(frontmatter_text)
    except Exception:
        logger.warning("Invalid frontmatter in style file: %s", path, exc_info=True)
        return None

    name = fm.get("name")
    if not name or not isinstance(name, str):
        logger.warning("Style file missing 'name' in frontmatter: %s", path)
        return None

    raw_tags = fm.get("tags", [])
    if isinstance(raw_tags, list):
        tags = tuple(str(t) for t in raw_tags)
    elif isinstance(raw_tags, str):
        tags = (raw_tags,)
    else:
        tags = ()

    provider = fm.get("provider")
    if isinstance(provider, str) and provider in ("auto", "null", "~"):
        provider = None if provider in ("null", "~") else provider

    aspect_ratio = fm.get("aspect_ratio")
    if aspect_ratio is not None:
        aspect_ratio = str(aspect_ratio)

    quality = fm.get("quality")
    if quality is not None:
        quality = str(quality)

    return StyleEntry(
        name=name,
        tags=tags,
        provider=provider if isinstance(provider, str) else None,
        aspect_ratio=aspect_ratio,
        quality=quality,
        body=body.strip(),
        file_path=path.resolve(),
    )


def scan_styles(directory: Path) -> dict[str, StyleEntry]:
    """Scan a directory for style markdown files.

    Creates the directory if it does not exist. Globs ``*.md`` files and
    parses each one via :func:`parse_style`. Files that fail to parse are
    skipped with a warning.

    Args:
        directory: Path to the styles directory.

    Returns:
        Dict mapping style name to :class:`StyleEntry`.
    """
    directory.mkdir(parents=True, exist_ok=True)

    styles: dict[str, StyleEntry] = {}
    for path in sorted(directory.glob("*.md")):
        entry = parse_style(path)
        if entry is not None:
            styles[entry.name] = entry

    logger.info("Scanned %d style(s) from %s", len(styles), directory)
    return styles
