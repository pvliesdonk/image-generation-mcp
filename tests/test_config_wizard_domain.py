"""Domain-specific config-wizard tests for Image Generation MCP.

This file is owned by the generated project (kept across ``copier update`` via
``_skip_if_exists``). Add assertions here that depend on *this project's*
``wizard-spec.json`` — browser assertions (a field renders, an option emits the
expected env var, a guard message appears; import the page/browser fixtures from
``test_config_wizard_smoke.py``), or pure-spec assertions like the coverage
invariant below. The generic framework tests live in
``test_config_wizard_smoke.py`` (template-owned) and must not be edited here.
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path

from image_generation_mcp.config import ProjectConfig

_ENV_PREFIX = "IMAGE_GENERATION_MCP"
_WIZARD_SPEC = (
    Path(__file__).resolve().parent.parent
    / "docs"
    / "javascripts"
    / "config-wizard"
    / "wizard-spec.json"
)


def _offered_vars() -> set[str]:
    """Every env var the wizard can set: question ``var``s + option ``emit`` keys."""
    spec = json.loads(_WIZARD_SPEC.read_text(encoding="utf-8"))
    out: set[str] = set()
    for q in spec["questions"]:
        if q.get("var"):
            out.add(q["var"])
        for opt in q.get("options", []):
            out.update((opt.get("emit") or {}).keys())
    return out


def test_deprecated_a1111_aliases_not_offered_but_still_read() -> None:
    """Pin the ``A1111_*`` ``_COVERED_BY_INFERENCE`` exemption to deliberate intent.

    The drift test exempts ``A1111_HOST``/``A1111_MODEL`` from wizard coverage
    because they are deprecated aliases of ``SD_WEBUI_HOST``/``SD_WEBUI_MODEL``.
    This asserts the exemption corresponds to a real, intentional state rather
    than coincidence: the wizard offers the canonical ``SD_WEBUI_*`` controls and
    never the deprecated names, while ``ProjectConfig.from_env`` still reads the
    aliases for back-compat. It fails (catching rot) if a wizard control for a
    deprecated alias is ever added, the canonical control is dropped, or the
    back-compat read is removed without retiring the exemption.
    """
    offered = _offered_vars()
    from_env_src = inspect.getsource(ProjectConfig.from_env)

    for legacy, canonical in (
        ("A1111_HOST", "SD_WEBUI_HOST"),
        ("A1111_MODEL", "SD_WEBUI_MODEL"),
    ):
        assert f"{_ENV_PREFIX}_{legacy}" not in offered, (
            f"deprecated {legacy} must not be a wizard control"
        )
        assert f"{_ENV_PREFIX}_{canonical}" in offered, (
            f"canonical {canonical} must be offered by the wizard"
        )
        assert f'"{legacy}"' in from_env_src, (
            f"{legacy} must still be read by from_env for back-compat "
            f"(or the _COVERED_BY_INFERENCE exemption should be retired)"
        )
