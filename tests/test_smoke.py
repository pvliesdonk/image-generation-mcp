"""Smoke test placeholder.

The template-generated version of this file imports from
``{python_module}.server`` — but IG's retrofit kept the older
``mcp_server`` module name, so the template's scaffold import fails.

This project's real tests live in the other ``tests/test_*.py`` files;
this file exists solely to satisfy ``_skip_if_exists`` in the template's
``copier.yml`` so future ``copier update`` runs don't re-create the
broken scaffold.
"""

from __future__ import annotations


def test_placeholder() -> None:
    """No-op marker test."""
    assert True
