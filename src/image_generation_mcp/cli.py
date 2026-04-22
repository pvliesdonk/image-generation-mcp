"""CLI entry point — thin shim around :mod:`image_generation_mcp._cli_impl`.

The real implementation lives in :mod:`._cli_impl` (project-owned, never
touched by copier update).  This module is intentionally tiny so the
template-owned ``cli.py`` patches from future ``copier update`` runs have
no shared context lines to apply against — the rejected hunks land in a
``.rej`` sidecar for the operator to triage.
"""

from image_generation_mcp._cli_impl import main

__all__ = ["main"]
