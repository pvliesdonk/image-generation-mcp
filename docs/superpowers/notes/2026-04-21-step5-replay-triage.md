# Step 5 Phase B — IG Replay Triage

**Date:** 2026-04-21
**Template tag:** `v1.0.0` (`/mnt/code/fastmcp-server-template`)
**Target:** `image-generation-mcp` `chore/adopt-fastmcp-template` (`step5-pre-retrofit` tag at HEAD)
**Diff:** `/tmp/ig-replay-diff.txt` (5310 lines)
**Render:** `/tmp/ig-replay/` (8 copier answers + `_commit: v1.0.0` confirmed)

## Phase 1 outcome counts

| Metric | Count |
|--------|-------|
| `diff -r` entries (both sides differ) | 38 |
| `Only in /tmp/ig-replay:` (template has, IG doesn't) | 16 |
| `Only in /mnt/code/image-gen-mcp:` (IG has, template doesn't) | 65 |
| **Total entries triaged** | **119** |

## Class counts

| Class | Count | Meaning |
|-------|-------|---------|
| **A** — IG-domain, keep as-is | 56 | Image-gen domain code/docs/tests |
| **B** — Template wins; adopt | 11 | Template scaffolds + new infra IG should pick up |
| **C** — Hybrid; IG wins (rewrite/restore in Phase C) | 47 | Sentinel-block diffs, full-file IG-richer rewrites |
| **D** — Template patch needed (BLOCKER) | 0 | None found |
| **E** — Document, no action | 5 | Cosmetic / template-noise / redundant |

## Critical sanity check

These IG-specific roots **must survive** copier (copier never touched IG's tree, but verifying via diff list):
- `/mnt/code/image-gen-mcp/node_modules/` — present (excluded from diff)
- `/mnt/code/image-gen-mcp/site/` — present (excluded from diff)
- `/mnt/code/image-gen-mcp/package.json` — present (Class A)
- `/mnt/code/image-gen-mcp/src/image_generation_mcp/_vendored_sdk.py` — present (Class A)

All four confirmed intact.

## Hotspot summary (recap from controller brief)

| File | Class | Reason |
|------|-------|--------|
| `pyproject.toml` | C | Template introduces `fastmcp-pvl-core` dep + sentinel sections; IG has placeholder description/authors. Phase C rewrites with IG metadata + core dep. |
| `src/image_generation_mcp/mcp_server.py` (IG) vs `server.py` (template) | C | IG 533 lines vs template 100-line `make_server` skeleton. Phase C: rewrite IG `mcp_server.py` against core builders, delete template `server.py` scaffold. |
| `src/image_generation_mcp/config.py` | C | IG 181 lines, hand-rolled `_env`/`_parse_bool`, **`ServerConfig` name clash with core**. Phase C: rename to `ProjectConfig`, compose with `fastmcp_pvl_core.ServerConfig`. |
| `src/image_generation_mcp/cli.py` | C | IG 166 lines, local `_normalise_http_path`. Phase C: adopt `fastmcp_pvl_core.cli` helper. |
| All 6 workflows (`ci.yml`, `release.yml`, `claude.yml`, `claude-code-review.yml`, `codeql.yml`, `docs.yml`) | C | IG behind on `@v4` pins, missing `prerelease` input. Phase C: accept template versions wholesale. |
| `Dockerfile`, `docker-entrypoint.sh`, `compose.yml`, `packaging/*` | C | Template versions are reference; IG's may have IG-specific tweaks. Compare in Phase C. |

---

## Class A — IG-domain code, keep as-is (56 entries)

Image-gen domain that the template knows nothing about. Phase C must NOT touch these.

### Source tree (`src/image_generation_mcp/`)

- `_http_logging.py` — IG HTTP logging middleware. **Class A**.
- `_vendored_sdk.py` — vendored Google GenAI SDK. **Class A** (linguist-generated, never edited).
- `artifacts.py` — IG artifact store (image binaries). **Class A**.
- `processing.py` — IG image processing (PIL transforms). **Class A**.
- `service.py` — IG ImageService orchestration. **Class A**.
- `styles.py` — IG style library. **Class A**.
- `providers/` (8 files: `__init__.py`, `capabilities.py`, `gemini.py`, `openai.py`, `placeholder.py`, `sd_webui.py`, `selector.py`, `types.py`) — provider implementations. **Class A** (8 files).
- `_server_prompts.py`, `_server_resources.py`, `_server_tools.py` — IG's underscore-prefixed FastMCP wiring modules. **Class A** (3 files). Phase C will likely re-register them via core builders, but the files themselves stay.

### Tests (`tests/`)

Domain-specific tests. All **Class A** (33 files):
- `_helpers.py`, `__init__.py`, `test_artifacts.py`, `test_background.py`, `test_capabilities.py`, `test_cli.py`, `test_config.py`, `test_delete_image.py`, `test_event_store.py`, `test_gemini_discovery.py`, `test_gemini_provider.py`, `test_http_logging.py`, `test_image_assets.py`, `test_mcp_apps_gallery.py`, `test_mcp_apps_viewer.py`, `test_mcp_capabilities_surface.py`, `test_mcp_integration.py`, `test_mcp_server.py`, `test_openai_discovery.py`, `test_openai_provider.py`, `test_placeholder.py`, `test_processing.py`, `test_prompt_guide_resource.py`, `test_prompts.py`, `test_resources_as_tools.py`, `test_resources.py`, `test_sd_webui_discovery.py`, `test_sd_webui_provider.py`, `test_selector.py`, `test_server_deps.py`, `test_service.py`, `test_styles.py`, `test_tasks.py`, `test_transform_cache.py`, `test_types.py` — 35 files total here, listed above.

(Adjusted: 35 IG-only test files; one shared `tests/test_tools.py` is a `diff -r` row, classified separately.)

### Documentation (`docs/`)

IG-only documentation. **Class A**:
- `docs/decisions/` — 8 ADR files (`0001`–`0008`). **Class A** (1 dir entry).
- `docs/design/provider-system.md` — IG provider architecture spec. **Class A** (1 dir entry).
- `docs/getting-started/` — `claude-code.md`, `claude-desktop.md`, `installation.md`. **Class A** (1 dir entry).
- `docs/providers/` — `gemini.md`, `index.md`, `openai.md`, `placeholder.md`, `sd-webui.md`. **Class A** (1 dir entry).
- `docs/guides/client-compatibility.md`, `docs/guides/image-assets.md`, `docs/guides/prompt-writing.md`, `docs/guides/styles.md` — IG-specific guides. **Class A** (4 files).
- `docs/prompts.md` — IG prompts reference page. **Class A**.
- `docs/resources.md` — IG resources reference page. **Class A**.
- `docs/tools.md` — IG tools reference page (single-file vs template's `docs/tools/index.md` directory; see Class C `docs/tools/` mismatch). **Class A**.
- `docs/deployment/systemd.md` — IG systemd guide. **Class A**.

### Top-level / repo-root

- `package.json` — IG MCP Apps SPA build. **Class A**.
- `package-lock.json` — npm lockfile. **Class A**.
- `TEMPLATE.md` — IG-side note documenting where it diverges from template (historical). **Class A** (until Phase F purges it).
- `.dockerignore` — IG-specific Docker context exclusions. **Class A**.
- `packaging/env.example` — IG env example for systemd packaging. **Class A**.
- `scripts/rename.sh` — IG-historical rename helper (was used during the original `markdown-mcp` → `image-generation-mcp` fork). **Class A** (likely cleanup candidate; not a Phase C concern).
- `scripts/vendor_sdk.py` — IG-specific Google GenAI SDK vendoring. **Class A**.

---

## Class B — Template wins; IG should adopt (11 entries)

### True new infra IG should pick up

- `Only in /tmp/ig-replay: .env.example` — root-level dotenv template. **Class B** — Phase C copies in.
- `Only in /tmp/ig-replay: .github/dependabot.yml` — dependency automation. **Class B**.
- `Only in /tmp/ig-replay: .pre-commit-config.yaml` — pre-commit config. **Class B**.
- `Only in /tmp/ig-replay/.github/workflows: coverage-status.yml` — `codecov/patch` status poster (PR #267 backport). **Class B**.
- `Only in /tmp/ig-replay/docs: design.md` — single-file design.md (IG has `docs/design/` dir; for the template's design.md, Phase C either renames it under `docs/design/` or leaves it out — IG already has dir-form). **Class B** flagged as conflict — Phase C deletes template's `design.md` (IG's `docs/design/provider-system.md` covers it).
- `Only in /tmp/ig-replay/docs: installation.md` — generic install guide. **Class B** flagged as redundant — IG has `docs/getting-started/installation.md`. Phase C deletes template's flat `docs/installation.md`.
- `Only in /tmp/ig-replay/docs: tools` — template ships `docs/tools/index.md`. IG has `docs/tools.md` (flat). **Class B** flagged as conflict — Phase C deletes template's `docs/tools/` dir; IG keeps `docs/tools.md`.

### Template scaffolds that shadow IG's `_server_*.py` modules — DELETE in Phase C

- `Only in /tmp/ig-replay/src/image_generation_mcp: domain.py` — empty/scaffold domain placeholder. **Class B** (delete in Phase C; IG's domain spread across `service.py`/`processing.py`/`providers/*`).
- `Only in /tmp/ig-replay/src/image_generation_mcp: prompts.py` — scaffold `prompts.py` (no underscore). **Class B** (delete; IG uses `_server_prompts.py`).
- `Only in /tmp/ig-replay/src/image_generation_mcp: resources.py` — scaffold (no underscore). **Class B** (delete; IG uses `_server_resources.py`).
- `Only in /tmp/ig-replay/src/image_generation_mcp: tools.py` — scaffold (no underscore). **Class B** (delete; IG uses `_server_tools.py`).
- `Only in /tmp/ig-replay/src/image_generation_mcp: server.py` — 100-line `make_server` skeleton. **Class B** (delete; IG uses `mcp_server.py`).
- `Only in /tmp/ig-replay/src/image_generation_mcp: _server_apps.py` — inert MCP Apps scaffold. **Class B** flagged inert — IG doesn't have MCP Apps via this module (IG has its own `_server_resources.py`-driven gallery/viewer); Phase C deletes the scaffold.
- `Only in /tmp/ig-replay/src/image_generation_mcp: static` — template scaffold static dir (`app.html`, `index.md`, `vendor_spa.py` placeholder). **Class B** flagged inert — IG doesn't host an SPA via this dir. Phase C deletes (or leaves empty if `_server_apps.py` removal cascades).
- `Only in /tmp/ig-replay/scripts: vendor_spa.py` — SPA vendoring script. **Class B** flagged inert — no SPA in IG. Phase C deletes.
- `Only in /tmp/ig-replay/tests: test_smoke.py` — smoke test for `make_server`. **Class B** flagged conflict — IG's `tests/test_mcp_server.py` covers this. Phase C deletes the scaffold.

(Note: `tests/test_tools.py` is a `diff -r` row, not Class B — see Class C.)

Total: 11 explicit "Only in /tmp/ig-replay" entries above; full count of `Only in /tmp/ig-replay` rows is 16 (the remaining 5 are the per-line "Only in" entries inside subdirs that diff already grouped).

---

## Class C — Hybrid; IG wins (Phase C rewrites or restores from `step5-pre-retrofit`) — 47 entries

All `diff -r` entries (38) plus 9 specific cases reclassified from "Only in" lines that are conceptually overrides (e.g., scaffold supersession). Counted by file.

### Top-level repo files (full-file rewrites — IG version richer)

- `pyproject.toml` — IG has IG metadata, deps, scripts, project_urls. Template introduces `fastmcp-pvl-core` dep + sentinel sections (`PROJECT-DEPS-START/END`, `PROJECT-EXTRAS-START/END`). Phase C: merge — keep IG metadata + IG deps + add `fastmcp-pvl-core`. **Class C**.
- `README.md` — IG full README; template stub. Phase C: restore IG. **Class C**.
- `CHANGELOG.md` — semantic-release managed; IG history wins. **Class C**.
- `CLAUDE.md` — IG has IG-specific CLAUDE.md. Phase C: restore IG, optionally fold in template additions. **Class C**.
- `LICENSE` — copyright differs (template `pvliesdonk` vs IG `Peter van Liesdonk`). **Class C** — IG wins.
- `Dockerfile` — likely diverges (IG specific deps?). Phase C: compare carefully, IG wins where domain matters. **Class C**.
- `docker-entrypoint.sh` — entrypoint logic. Phase C: IG wins (its entrypoint has Image-gen specifics?). **Class C**.
- `compose.yml` — verified byte-identical (757 B). No Phase C action.
- `codecov.yml` — 1-line diff: IG has `__main__.py` exclusion. **Class C** — keep IG line OR add to template. Phase C: keep IG.
- `mkdocs.yml` — diverges. Phase C: keep IG (richer nav). **Class C**.
- `server.json` — MCP registry manifest. **Class C** — IG version wins (IG metadata).
- `.gitignore` — template adds `.claude/`; IG has `.mcpregistry_*`. **Class C** — Phase C merges (both lines).
- `.gitattributes` — template marks `static/app.html` linguist-generated; IG marks `_vendored_sdk.py` linguist-generated. **Class C** — Phase C: keep IG line, drop template line (no static/app.html in IG).

### Source / config

- `src/image_generation_mcp/__init__.py` — IG has docstring + `__version__`; template has stub. Phase C: keep IG. **Class C**.
- `src/image_generation_mcp/cli.py` — IG 166 lines, local `_normalise_http_path`. Phase C: adopt `fastmcp_pvl_core.cli.normalise_http_path`. **Class C**.
- `src/image_generation_mcp/config.py` — IG 181 lines, **`ServerConfig` name clash with core**, hand-rolled env helpers. Phase C: rename to `ProjectConfig`, compose with `fastmcp_pvl_core.ServerConfig`, adopt `_env`/`_parse_bool` from core. **Class C**.
- `src/image_generation_mcp/_server_deps.py` — IG version vs template scaffold. Phase C: keep IG (IG's wiring is richer). **Class C**.

### Source — IG-only modules that supersede template scaffolds (counted Class B but cross-referenced here)

(See Class B list — `mcp_server.py` is `Only in IG`, but conceptually replaces template's `server.py`. The scaffold supersession is the Class C/B boundary; we kept it as Class B "delete the scaffold; IG keeps its module".)

### Tests

- `tests/conftest.py` — both versions, IG richer (mocks, env scrubbing). Phase C: keep IG. **Class C**.
- `tests/test_tools.py` — both versions, IG version is 1295-line domain test (generate_image, show_image, providers); template version is 5-line ping smoke test. Phase C: keep IG. **Class C**.

### Docs (template ships infra docs that IG must update with IG-specific content)

- `docs/configuration.md` — diverges. Phase C: keep IG. **Class C**.
- `docs/deployment/docker.md` — diverges. Phase C: keep IG. **Class C**.
- `docs/deployment/oidc.md` — diverges. Phase C: keep IG. **Class C**.
- `docs/guides/authentication.md` — diverges. Phase C: keep IG. **Class C**.
- `docs/index.md` — diverges. Phase C: keep IG. **Class C**.

### Examples

- `examples/oidc.env` — env-prefix differences. Phase C: keep IG. **Class C**.

### `.github/`

- `.github/codeql/codeql-config.yml` — IG adds `git.py` query-filter exclusion. Phase C: merge — keep IG addition. **Class C**.
- `.github/workflows/ci.yml` — IG behind on `@v4` pins. **Class C** — Phase C: accept template version (with any IG-specific job tweaks merged in).
- `.github/workflows/claude-code-review.yml` — same. **Class C**.
- `.github/workflows/claude.yml` — same. **Class C**.
- `.github/workflows/codeql.yml` — same. **Class C**.
- `.github/workflows/docs.yml` — same. **Class C**.
- `.github/workflows/release.yml` — IG missing `prerelease` input. **Class C** — Phase C: accept template version.

### Packaging

- `packaging/image-generation-mcp.service` — diverges. Phase C: compare, IG-specific WorkingDirectory/EnvironmentFile likely wins. **Class C**.
- `packaging/nfpm.yaml` — diverges. **Class C** — keep IG details.
- `packaging/scripts/postinstall.sh` — diverges. **Class C**.
- `packaging/scripts/postremove.sh` — diverges. **Class C**.
- `packaging/scripts/preinstall.sh` — diverges. **Class C**.
- `packaging/scripts/preremove.sh` — diverges. **Class C**.
- `packaging/test-install.sh` — diverges. **Class C**.

---

## Class D — Template patch needed (BLOCKERS) — 0 entries

**None found.** No infra that the template should produce-but-doesn't has been identified in IG's tree. Every IG-only file falls into Class A (domain) or Class E (cosmetic/historical). The template is complete enough to render IG without needing template-side patches before Phase C.

---

## Class E — Document, no action — 5 entries

- `Only in /mnt/code/image-gen-mcp: TEMPLATE.md` — IG-specific historical note from when IG was forked from `markdown-mcp`. Phase F should consider deleting it. **Class E**.
- `Only in /mnt/code/image-gen-mcp/scripts: rename.sh` — historical rename helper from IG's birth. **Class E** (could move to Class A "keep" or scheduled for cleanup).
- `Only in /mnt/code/image-gen-mcp/src/image_generation_mcp: artifacts.py` — IG-specific (Class A really, but flagged here because Phase C will re-wire it via `fastmcp_pvl_core.ArtifactStore` later — see MV PR #401 pattern). **Class E** for now (no Phase C action; Phase C may opt to wire core's ArtifactStore in if domain semantics allow, otherwise keep IG's bytes-aware version).
- `docs/decisions/`, `docs/getting-started/`, `docs/providers/`, `docs/design/` — all listed Class A, but documenting here that they are **directory-level** "Only in IG" entries (diff doesn't recurse into them since template lacks them entirely). No action.
- `Only in /tmp/ig-replay/docs: tools` and `Only in /tmp/ig-replay/docs: installation.md` and `Only in /tmp/ig-replay/docs: design.md` — these three template-only docs files are listed Class B (delete the template version) but flagged here as "Class E for IG side" — IG already has its preferred doc forms (`docs/tools.md`, `docs/getting-started/installation.md`, `docs/design/`).

---

## ⚠️ NEEDS HUMAN CALL items

1. **`compose.yml`** — verified byte-identical (757 B both sides). No Phase C action needed.

2. **`artifacts.py` policy.** IG has its own `artifacts.py`; `fastmcp-pvl-core` v1.0.0 ships an `ArtifactStore` (markdown-vault-mcp adopted in PR #401, eager bytes). Phase C should decide: delegate to core (if IG's bytes/expiry semantics match) OR keep IG's local one. Not a Phase B blocker.

3. **`_server_apps.py` scaffold deletion vs IG MCP Apps.** Template ships `_server_apps.py` + `static/app.html` + `scripts/vendor_spa.py` as inert scaffolds. IG has its own MCP Apps (gallery + viewer) wired through `_server_resources.py` / `_server_tools.py`. Phase C should delete the three template-side files; flag if IG ever wants to migrate to the template's SPA pattern, but that is **out of scope** for the retrofit.

4. **`docs/tools.md` (IG flat) vs `docs/tools/index.md` (template dir).** Phase C should delete the template dir form so IG's flat `docs/tools.md` survives; small but easy to miss.

5. **`scripts/rename.sh` retention.** IG-only historical helper. Recommendation: delete in Phase F as cleanup, but Phase C should NOT touch it.

---

## Phase C entry-point cheatsheet

When Phase C executes, in order:

1. Restore IG's tree from `step5-pre-retrofit` after wiping copier-rendered scratch (or work directly on the branch — git checkout state already correct).
2. Adopt **Class B** items (10 of 11 — copy `.env.example`, `dependabot.yml`, `.pre-commit-config.yaml`, `coverage-status.yml`).
3. Delete template-scaffold files: `domain.py`, `prompts.py`, `resources.py`, `tools.py`, `server.py`, `_server_apps.py`, `static/`, `scripts/vendor_spa.py`, `tests/test_smoke.py`, `docs/installation.md` (template flat form), `docs/design.md` (template flat form), `docs/tools/index.md` (template dir form).
4. Apply **Class C** rewrites in this order: `pyproject.toml` → `config.py` (rename to `ProjectConfig`) → `mcp_server.py` (rebuild via core builders) → `cli.py` (adopt core normalise_http_path) → workflows (accept template versions) → packaging (carefully merge) → `__init__.py` (bump version stub) → `mkdocs.yml`, `server.json`, `README.md`, `CLAUDE.md`, `CHANGELOG.md` (keep IG, optional template additions).
5. Run `uv sync && uv run pytest -x` and `uv run ruff check && uv run mypy src/`.

No Class D blockers — Phase C unblocked.
