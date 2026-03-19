"""Pytest configuration and shared fixtures."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove all MCP_IMAGEGEN_* env vars before each test.

    Prevents env var leakage between tests that call :func:`create_server`.
    """
    import os

    for key in list(os.environ):
        if key.startswith("MCP_IMAGEGEN_"):
            monkeypatch.delenv(key, raising=False)
