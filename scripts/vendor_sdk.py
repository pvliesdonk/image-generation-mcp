#!/usr/bin/env python3
"""Vendor the MCP Apps ext-apps SDK for offline use.

Downloads the pinned SDK version, verifies its integrity, and writes a
Python module containing the base64-encoded bundle.  The generated module
is imported by ``_server_resources.py`` to build an ES import-map that
replaces the runtime CDN dependency.

Usage::

    python scripts/vendor_sdk.py          # Generate _vendored_sdk.py
    python scripts/vendor_sdk.py --check  # Verify _vendored_sdk.py is up-to-date
"""

from __future__ import annotations

import base64
import hashlib
import sys
import urllib.error
import urllib.request
from pathlib import Path

# ---------------------------------------------------------------------------
# Pinned dependency — bump version + hash when upgrading
# ---------------------------------------------------------------------------

SDK_VERSION = "1.3.1"
SDK_URL = (
    "https://unpkg.com/"
    f"@modelcontextprotocol/ext-apps@{SDK_VERSION}/app-with-deps"
)
SDK_SHA256 = "36495489aa8939e4eb7421c8a03c220b9f502d79e87895f88599eb6c02377fdd"
SDK_IMPORT_SPECIFIER = "@modelcontextprotocol/ext-apps"

_OUT_PATH = (
    Path(__file__).resolve().parent.parent
    / "src"
    / "image_generation_mcp"
    / "_vendored_sdk.py"
)

_HEADER = '"""Vendored @modelcontextprotocol/ext-apps SDK — auto-generated.\n\nDo not edit manually.  Regenerate with::\n\n    python scripts/vendor_sdk.py\n"""'


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _download(url: str) -> bytes:
    """Download *url* and return its raw bytes."""
    req = urllib.request.Request(url, headers={"User-Agent": "vendor-sdk/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read()
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
        raise SystemExit(f"ERROR: failed to download {url}: {exc}") from exc


def _expected_content() -> str:
    """Build the expected file content from current config (without downloading)."""
    # Read the existing base64 from the generated file (if it exists) for
    # --check mode.  We only need to verify the config hash matches.
    return f"VERSION = {SDK_VERSION!r}\nIMPORT_SPECIFIER = {SDK_IMPORT_SPECIFIER!r}"


def _config_hash() -> str:
    """Hash of pinned config fields — changes when version/URL/hash are bumped."""
    h = hashlib.sha256()
    h.update(f"version={SDK_VERSION}".encode())
    h.update(f"url={SDK_URL}".encode())
    h.update(f"sha256={SDK_SHA256}".encode())
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    """Entry point.  Returns 0 on success, 1 on failure."""
    check_mode = "--check" in sys.argv
    marker = f"# vendor-sdk-config-hash:{_config_hash()}"

    if check_mode:
        if not _OUT_PATH.exists():
            print(
                f"ERROR: {_OUT_PATH} does not exist — "
                "run  python scripts/vendor_sdk.py  to generate it.",
                file=sys.stderr,
            )
            return 1
        content = _OUT_PATH.read_text(encoding="utf-8")
        if marker in content:
            print("OK: _vendored_sdk.py is up-to-date.")
            return 0
        print(
            "ERROR: _vendored_sdk.py is out of date — "
            "run  python scripts/vendor_sdk.py  to regenerate.",
            file=sys.stderr,
        )
        return 1

    # Download and verify
    print(f"  Downloading ext-apps SDK v{SDK_VERSION} …")
    raw = _download(SDK_URL)
    sha = hashlib.sha256(raw).hexdigest()
    print(f"    {len(raw):,} bytes  SHA-256: {sha[:16]}…")

    if sha != SDK_SHA256:
        print(
            f"ERROR: SHA-256 mismatch for ext-apps@{SDK_VERSION}\n"
            f"  expected: {SDK_SHA256}\n"
            f"  got:      {sha}",
            file=sys.stderr,
        )
        return 1

    try:
        raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SystemExit(
            f"ERROR: SDK download is not valid UTF-8: {exc}"
        ) from exc

    b64 = base64.b64encode(raw).decode("ascii")

    # Write the vendored module
    lines = [
        _HEADER,
        "",
        marker,
        "",
        f"VERSION = {SDK_VERSION!r}",
        f"IMPORT_SPECIFIER = {SDK_IMPORT_SPECIFIER!r}",
        "",
        f'SDK_BASE64 = "{b64}"',
        "",
    ]
    _OUT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nWrote {_OUT_PATH} ({_OUT_PATH.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
