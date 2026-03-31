# ADR-0008: Style Library

## Status

Accepted

## Context

Users want reusable style presets for different contexts (business
presentations, website assets, social media). Each provider has fundamentally
different prompt formats — OpenAI uses natural language, A1111/SD WebUI uses
CLIP tags with negative prompts. A style cannot be a prompt template; it must
be a descriptive document that the LLM adapts to the target provider at
generation time.

Key requirements:

- Styles must be human-readable and editable outside the MCP server
- Styles must work across all providers without provider-specific variants
- The LLM must interpret styles as creative direction, not copy them verbatim
- Users must be able to manage styles from within an MCP conversation

## Decision Drivers

- **Provider heterogeneity** -- OpenAI, SD WebUI (CLIP vs Flux), and
  Placeholder have incompatible prompt formats
- **Human authoring** -- users should be able to create and edit styles in
  any text editor
- **LLM interpretation** -- styles are creative briefs for the LLM to
  interpret, not prompt fragments for mechanical prepending
- **Simplicity** -- flat directory, no database, no nested hierarchies

## Considered Options

### Option 1: JSON-only format

Styles stored as `.json` files with structured prompt fields.

**Pros:** Easy to parse, schema-validatable.
**Cons:** Poor authoring experience for prose-heavy creative briefs. JSON
escaping makes multiline text unreadable.

### Option 2: Structured prompt templates

Styles contain per-provider prompt templates with variable interpolation.

**Pros:** Precise control over provider-specific output.
**Cons:** Defeats the purpose of LLM interpretation. Requires maintaining
parallel templates for each provider. Breaks when new providers are added.

### Option 3: Provider-specific style variants

Each style has a separate file per provider (e.g. `website-openai.md`,
`website-sd_webui.md`).

**Pros:** Maximum provider-specific tuning.
**Cons:** Maintenance burden scales with providers × styles. Users must
understand each provider's prompt format. Violates the "creative brief"
principle.

### Option 4: Markdown files with YAML frontmatter (chosen)

Styles are markdown files with YAML frontmatter for structured metadata and
prose body for the creative brief.

**Pros:** Human-readable, easy to author, familiar format (like Jekyll/Hugo
posts). Frontmatter carries optional defaults. Body is free-form prose that
the LLM interprets per-provider.
**Cons:** Requires YAML parser. Frontmatter schema is loosely enforced.

## Decision

**Option 4: Markdown files with YAML frontmatter.**

### File Format

Each style is a `.md` file with YAML frontmatter and a markdown body:

```markdown
---
name: website
tags: [brand, web, modern]
provider: auto
aspect_ratio: "16:9"
quality: hd
---

Minimalist flat illustration. Geometric shapes, clean lines.
Brand palette: deep teal (#0D4F4F), warm cream (#F5F0E8), coral accent (#FF6B5E).
Plenty of negative space. No photorealism, no gradients, no text in image.
Suitable for hero banners and section dividers.
```

### Frontmatter Schema

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `name` | `str` | Yes | -- | Style identifier (must match filename without `.md`) |
| `tags` | `list[str]` | No | `[]` | Categorization tags for filtering/browsing |
| `provider` | `str` | No | `"auto"` | Suggested provider (`"auto"`, `"openai"`, `"sd_webui"`, etc.) |
| `aspect_ratio` | `str` | No | `null` | Default aspect ratio (e.g. `"16:9"`) |
| `quality` | `str` | No | `null` | Default quality level (`"standard"` or `"hd"`) |

### Directory Layout

Single flat directory, configurable via environment variable:

- **Default:** `~/.image-generation-mcp/styles/`
- **Env var:** `IMAGE_GENERATION_MCP_STYLES_DIR`
- **Scanning:** glob `*.md` files in the directory
- **Auto-creation:** directory is created if it does not exist

No nested directories — all styles live in the top-level directory.

### MCP Surface

| Component | Type | Name | Description |
|-----------|------|------|-------------|
| Resource | static | `style://list` | JSON array of all styles (name, tags, description, defaults) |
| Resource | template | `style://{name}` | Full markdown content of a specific style |
| Tool | write | `save_style` | Create or overwrite a style file from conversation |
| Tool | write | `delete_style` | Remove a style file |
| Prompt | -- | `apply_style` | Guidance for LLM to interpret a style as a creative brief |

### Key Design Principle

**Styles are creative briefs for LLM interpretation, not prompt fragments for
mechanical prepending.**

The LLM reads the style's prose body, extracts visual direction (palette,
composition, mood, constraints), and composes a provider-appropriate prompt
incorporating that direction. For OpenAI, it writes natural language. For
SD WebUI with CLIP models, it writes comma-separated tags with negative
prompts. The style text is never copied verbatim into the generation prompt.

This design is necessitated by provider heterogeneity: a single style must
work across providers with incompatible prompt formats.

## Consequences

### Positive

- Human-readable, editable style files that work with any text editor
- Single style definition works across all providers via LLM interpretation
- Frontmatter defaults reduce repetitive parameter specification
- Markdown body allows rich creative direction with formatting
- Simple file-based storage with no database dependency

### Negative

- YAML frontmatter parsing requires either `pyyaml` (third-party dependency)
  or a custom regex/manual parser to avoid adding a new dependency
- Style quality depends on LLM interpretation quality
- No schema enforcement on body content (by design — creative briefs are
  free-form)
- No style versioning or history (out of scope)

### Future Extensions

- Style sharing/import/export between users
- Style inheritance (base style + overrides)
- Multi-style blending
- Automatic style suggestion based on user intent
