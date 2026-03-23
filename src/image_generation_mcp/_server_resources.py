"""MCP resource registrations.

Exposes provider capabilities, image assets, metadata, and the MCP Apps
image viewer as MCP resources.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from fastmcp import FastMCP
from fastmcp.dependencies import Depends
from fastmcp.resources import ResourceContent, ResourceResult
from fastmcp.server.apps import AppConfig, ResourceCSP
from mcp.types import Icon

from image_generation_mcp._server_deps import get_service
from image_generation_mcp.providers.types import (
    SUPPORTED_ASPECT_RATIOS,
    SUPPORTED_BACKGROUNDS,
    SUPPORTED_QUALITY_LEVELS,
    ImageProviderError,
)
from image_generation_mcp.service import ImageService

logger = logging.getLogger(__name__)

_LUCIDE = "https://unpkg.com/lucide-static/icons/{}.svg"
_IMAGE_VIEWER_URI = "ui://image-viewer/view.html"

_PROMPT_GUIDE = """\
# Image Generation Prompt Guide

## General Tips

**Aspect ratio:** Choose based on content — `16:9` for landscapes and banners,
`9:16` for portraits and mobile, `3:2` for photos, `1:1` for icons and avatars.

**Quality levels:** Use `standard` for drafts and iteration. Use `hd` for final
output (only affects OpenAI — SD WebUI and placeholder ignore this parameter).

**Negative prompts:** Use them when you want to explicitly exclude unwanted
elements. Most effective on SD WebUI (native CLIP support). On OpenAI, they are
appended as an "Avoid:" clause with weaker effect. Placeholder ignores them.

**Background:** Set `background="transparent"` when generating assets for
compositing (logos, icons, stickers). Supported by OpenAI (gpt-image-1) and
placeholder. SD WebUI ignores this parameter.

## OpenAI (gpt-image-1 / dall-e-3)

Natural language descriptions work well — write prompts as you would describe a
scene to a person. No need for comma-separated tags.

**Negative prompts:** Use an `"Avoid:"` clause appended to the prompt text,
e.g. `"Avoid: blurry, low resolution, watermark"`. The effect is weaker than
native negative prompt support.

**Strengths:** Text rendering, logos, typography, posters, banners, signs.
Also strong at general-purpose generation and following complex instructions.

**Style keywords:** Include style direction in natural language — "photorealistic",
"cinematic", "watercolor", "digital art", "minimalist", "flat design", "isometric",
"pixel art". These steer the aesthetic without needing CLIP tags.

**Text rendering tips:** Enclose exact text in quotes within the prompt, e.g.
`'a coffee shop sign that says "OPEN"'`. Specify font style if needed:
"bold sans-serif", "handwritten", "neon sign lettering".

**Quality levels:** `standard` and `hd` are both supported. `gpt-image-1`
maps both to its highest quality tier.

## SD WebUI / Stable Diffusion

SD WebUI supports multiple model architectures with different prompt styles.
Check `list_providers` to see each model's `prompt_style` field (`"clip"` or
`"natural_language"`).

### SD 1.5 / SDXL (CLIP-based models)

Use comma-separated CLIP tags for best results. Order tags by importance —
tokens near the front of the prompt have the most influence.

**Tag order:** `subject, medium, style, lighting, camera, quality tags`

**Example prompts:**

Portrait:
```
1girl, long hair, blue eyes, school uniform, standing, cherry blossoms,
soft lighting, detailed face, masterpiece, best quality
```

Landscape:
```
mountain landscape, sunset, dramatic clouds, lake reflection,
cinematic lighting, wide angle, 8k, highly detailed
```

Product shot:
```
white sneakers, product photography, studio lighting, white background,
sharp focus, commercial photography, high resolution
```

**Quality tags:** Add these to improve output quality:
- `masterpiece, best quality` — general quality boost
- `highly detailed, sharp focus` — detail enhancement
- `8k, ultra high res` — resolution boost (use sparingly)
- `professional, award winning` — style refinement

**Negative prompt template:**

General-purpose:
```
lowres, bad anatomy, bad hands, text, error, missing fingers,
extra digit, fewer digits, cropped, worst quality, low quality,
normal quality, jpeg artifacts, signature, watermark, blurry
```

For photorealism, add: `cartoon, anime, illustration, painting, drawing, art, sketch`

For anime/illustration, add: `photo, realistic, 3d render`

**BREAK syntax:** Use `BREAK` to split long prompts into separate CLIP chunks,
giving each concept its own 77-token budget:
```
1girl, detailed face, blue eyes BREAK
forest background, sunlight through trees BREAK
masterpiece, best quality, sharp focus
```

**CLIP token limits:**
- SD 1.5: 77 tokens per chunk. Front-load the most important tags.
- SDXL: 77 tokens per chunk, two CLIP encoders (ViT-L + ViT-bigG).

**Model-specific advice:**
- **SD 1.5** — Best at 768px base resolution, 30 steps, CFG 7.0. Good for anime,
  illustration, and stylized content. Smaller model, faster generation.
- **SDXL** — Best at 1024px base resolution, 35 steps, CFG 7.5. Better for
  photorealism and high-detail scenes. Use for final-quality output.
- **SDXL Lightning/Turbo** — Distilled models, only 6 steps needed, CFG 2.0.
  Very fast but less controllable. Good for rapid iteration.

### Flux (natural language)

Flux models use a T5 text encoder, NOT CLIP. Write prompts as natural language
descriptions — the same style as OpenAI.

**Key differences from SD 1.5 / SDXL:**
- Use complete sentences, not comma-separated tags
- Do NOT include quality tags (`masterpiece`, `best quality`) — meaningless to Flux
- Do NOT write a negative prompt — Flux does not support them
- Do NOT use `BREAK` syntax — Flux does not use CLIP chunking
- CFG scale and sampler are handled automatically by the server

**Example prompts:**

Portrait:
```
A young woman with long flowing hair and striking blue eyes wearing a
school uniform, standing beneath cherry blossom trees with soft natural
light filtering through the petals
```

Landscape:
```
A dramatic mountain landscape at sunset with towering peaks reflected in
a perfectly still alpine lake, storm clouds lit orange and purple by the
setting sun
```

Product shot:
```
A pair of pristine white sneakers on a clean white background, shot from
a three-quarter angle with professional studio lighting and crisp focus
```

**Flux Schnell vs Flux Dev:**
- **Flux Schnell:** 4 steps, fastest generation. Good for drafts and iteration.
- **Flux Dev:** 20 steps, higher quality. Use for final output.

## Placeholder

Use for quick testing, mock-ups, and zero-cost drafts. The placeholder
provider produces solid-color PNG images — the color is selected from a
6-color palette via SHA-256 hash of the prompt text, so the same prompt
always produces the same color. Supports `background="transparent"` for
RGBA output with alpha=0.

## Provider Selection

1. **Text, logos, typography** → `openai`
2. **Photorealism, portraits, product shots** → prefer `sd_webui`, fall back to `openai`
3. **Anime, illustration, painting, art** → prefer `sd_webui`, fall back to `openai`
4. **Quick test or placeholder** → `placeholder`
5. **General requests** → `openai` (most versatile, default)

Use `provider="auto"` for automatic selection, or specify a provider directly.
Call `list_providers` to see which providers are currently available.
"""

_IMAGE_VIEWER_HTML = """\
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="color-scheme" content="light dark">
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: system-ui, -apple-system, sans-serif;
      display: flex; flex-direction: column; align-items: center;
      padding: 16px; background: transparent;
    }
    #placeholder {
      color: #888; font-size: 14px; padding: 40px;
      text-align: center;
    }
    #viewer { display: none; width: 100%; max-width: 640px; }
    #viewer img {
      width: 100%; height: auto; border-radius: 8px;
      box-shadow: 0 2px 12px rgba(0,0,0,0.15);
    }
    #meta {
      margin-top: 12px; font-size: 12px; color: #666;
      line-height: 1.6; width: 100%; white-space: pre-wrap;
    }
    #download {
      display: inline-block; margin-top: 10px; padding: 6px 14px;
      font-size: 12px; font-weight: 500; text-decoration: none;
      color: #fff; background: #2563eb; border-radius: 6px;
    }
    #download:hover { background: #1d4ed8; }
    @media (prefers-color-scheme: dark) {
      #download { background: #3b82f6; }
      #download:hover { background: #2563eb; }
      #meta { color: #aaa; }
      #placeholder { color: #777; }
    }
  </style>
</head>
<body>
  <div id="placeholder">Waiting for image generation&hellip;</div>
  <div id="viewer">
    <img id="image" alt="Generated image">
    <div id="meta"></div>
    <a id="download" style="display:none" target="_blank" rel="noopener">Download full resolution</a>
  </div>
  <script type="module">
    import { App } from
      "https://unpkg.com/@modelcontextprotocol/ext-apps@0.4.0/app-with-deps";

    const app = new App({ name: "Image Viewer", version: "1.0.0" });

    let rendered = false;
    let imageKey = null;
    const STORE = "imgview:";
    const MAX_ENTRIES = 5;

    function extractImageKey(uri) {
      if (!uri) return null;
      const m = uri.match(/^image:\\/\\/([^/?]+)/);
      return m ? m[1] : null;
    }

    function storeKeys() {
      const keys = [];
      for (let i = 0; i < localStorage.length; i++) {
        const k = localStorage.key(i);
        if (k && k.startsWith(STORE)) keys.push(k);
      }
      return keys;
    }

    function saveState(key, img, text) {
      if (!key) return;
      const fullKey = STORE + key;
      const value = JSON.stringify({ img, text });
      try {
        localStorage.setItem(fullKey, value);
      } catch (e) {
        // Quota exceeded — evict oldest entries and retry
        const keys = storeKeys().filter(k => k !== fullKey);
        while (keys.length > 0) {
          localStorage.removeItem(keys.shift());
          try { localStorage.setItem(fullKey, value); return; } catch (_) {}
        }
        console.warn("Image viewer: localStorage quota exceeded", e);
      }
      // Enforce LRU cap
      const all = storeKeys().filter(k => k !== fullKey);
      while (all.length >= MAX_ENTRIES) {
        localStorage.removeItem(all.shift());
      }
    }

    function loadState(key) {
      if (!key) return null;
      try {
        const raw = localStorage.getItem(STORE + key);
        return raw ? JSON.parse(raw) : null;
      } catch (e) { console.warn("Image viewer: failed to load cached state", e); return null; }
    }

    function render(img, text) {
      const imgEl = document.getElementById("image");

      if (img) {
        imgEl.src = `data:${img.mimeType};base64,${img.data}`;
        document.getElementById("placeholder").style.display = "none";
        document.getElementById("viewer").style.display = "block";
      }

      if (text) {
        try {
          const meta = JSON.parse(text.text);
          if (meta.prompt) {
            imgEl.alt = meta.prompt;
          }
          const parts = [];
          if (meta.provider) {
            let providerStr = `Provider: ${meta.provider}`;
            if (meta.model) providerStr += ` (${meta.model})`;
            parts.push(providerStr);
          }
          if (meta.dimensions) parts.push(`${meta.dimensions[0]}\u00d7${meta.dimensions[1]}`);
          if (meta.original_size_bytes) {
            const kb = (meta.original_size_bytes / 1024).toFixed(1);
            parts.push(`${kb} KB`);
          }
          document.getElementById("meta").textContent =
            (meta.prompt ? `"${meta.prompt}"\\n` : "") +
            parts.join(" \\u00b7 ");
          const dlEl = document.getElementById("download");
          if (meta.download_url) {
            dlEl.href = meta.download_url;
            dlEl.style.display = "inline-block";
          } else {
            dlEl.style.display = "none";
          }
        } catch (e) { console.warn("Image viewer: failed to parse metadata", e); }
      }

      rendered = true;
    }

    app.ontoolinput = (params) => {
      imageKey = extractImageKey(params?.arguments?.uri);
      if (imageKey && !rendered) {
        const saved = loadState(imageKey);
        if (saved) render(saved.img, saved.text);
      }
    };

    app.ontoolresult = ({ content }) => {
      const img = content?.find(c => c.type === "image");
      const text = content?.find(c => c.type === "text");
      // Always render live result — it takes precedence over cached state
      render(img, text);
      let key = imageKey;
      if (!key && text) {
        try { key = JSON.parse(text.text).image_id; } catch (e) { console.warn("Image viewer: failed to get image_id from tool result", e); }
      }
      // Strip download_url before persisting — tokens expire after 5 min
      let persistText = text;
      if (text && text.text) {
        try {
          const parsed = JSON.parse(text.text);
          delete parsed.download_url;
          persistText = Object.assign({}, text, { text: JSON.stringify(parsed, null, 2) });
        } catch (e) { console.warn("Image viewer: failed to strip download_url before persisting", e); }
      }
      if (key) saveState(key, img, persistText);
    };

    await app.connect();
  </script>
</body>
</html>"""


def register_resources(mcp: FastMCP) -> None:
    """Register all MCP resources on *mcp*.

    Args:
        mcp: The :class:`~fastmcp.FastMCP` instance to register resources on.
    """

    @mcp.resource(
        "info://prompt-guide",
        description=(
            "Provider-specific prompt writing tips. Read before using "
            "SD WebUI/Stable Diffusion to learn CLIP tag format, quality "
            "tags, and negative prompt templates. Also covers OpenAI "
            "prompt style and provider selection guidance."
        ),
        mime_type="text/markdown",
        icons=[Icon(src=_LUCIDE.format("book-open-text"), mimeType="image/svg+xml")],
    )
    def prompt_guide() -> str:
        """Return per-provider prompt writing guidance as Markdown.

        Returns:
            Markdown text with per-provider prompt writing tips.
        """
        return _PROMPT_GUIDE

    @mcp.resource(
        "info://providers",
        description=(
            "Read this to discover which image providers are configured "
            "and what aspect ratios and quality levels are supported."
        ),
        icons=[Icon(src=_LUCIDE.format("info"), mimeType="image/svg+xml")],
    )
    async def provider_capabilities(
        service: ImageService = Depends(get_service),
    ) -> str:
        """Available image generation providers and their capabilities.

        Returns:
            JSON with provider names, availability, and supported features.
        """
        providers = service.list_providers()
        return json.dumps(
            {
                "providers": providers,
                "supported_aspect_ratios": SUPPORTED_ASPECT_RATIOS,
                "supported_quality_levels": SUPPORTED_QUALITY_LEVELS,
                "supported_backgrounds": SUPPORTED_BACKGROUNDS,
            },
            indent=2,
        )

    @mcp.resource(
        "image://{image_id}/view{?format,width,height,quality}",
        mime_type="application/octet-stream",
        description=(
            "Retrieve a generated image with optional transforms. "
            "No query params returns the original. Add format, width, "
            "height, or quality params to transform on the fly."
        ),
        icons=[Icon(src=_LUCIDE.format("scan-eye"), mimeType="image/svg+xml")],
    )
    async def image_view(
        image_id: str,
        format: str = "",
        width: int = 0,
        height: int = 0,
        quality: int = 90,
        service: ImageService = Depends(get_service),
    ) -> ResourceResult:
        """Retrieve an image with optional format conversion and resize.

        No parameters returns the original bytes unchanged. Set ``format``
        for conversion, ``width``/``height`` for resize or crop.

        Both width and height → center-crop to exact dimensions.
        Only width → proportional resize by width.
        Only height → proportional resize by height.

        Args:
            image_id: Image registry ID.
            format: Target format (``png``, ``webp``, ``jpeg``), or empty
                for original.
            width: Target width in pixels, or 0 for original.
            height: Target height in pixels, or 0 for original.
            quality: Compression quality for lossy formats (1-100).

        Returns:
            Image bytes with appropriate MIME type.
        """
        data, content_type = service.get_transformed_image(
            image_id, format=format, width=width, height=height, quality=quality
        )
        return ResourceResult([ResourceContent(content=data, mime_type=content_type)])

    @mcp.resource(
        "image://{image_id}/metadata",
        mime_type="application/json",
        description=(
            "Read generation provenance for an image — prompt, provider, "
            "parameters, and timestamps. Use after generate_image to "
            "inspect what was generated."
        ),
        icons=[Icon(src=_LUCIDE.format("file-json"), mimeType="image/svg+xml")],
    )
    async def image_metadata(
        image_id: str,
        service: ImageService = Depends(get_service),
    ) -> str:
        """Retrieve generation metadata for an image.

        Args:
            image_id: Image registry ID.

        Returns:
            JSON with generation provenance (prompt, provider, params).
        """
        record = service.get_image(image_id)

        # Read sidecar JSON directly
        sidecar_path = service.scratch_dir / f"{record.id}.json"
        try:
            return sidecar_path.read_text()
        except FileNotFoundError:
            raise ImageProviderError(
                "server",
                f"Metadata file missing for image '{image_id}'. "
                "Verify the image_id via image://list.",
            ) from None

    @mcp.resource(
        "image://list",
        mime_type="application/json",
        description=(
            "List all generated images with their IDs, resource URIs, "
            "and prompts. Read this to find image_ids for use with "
            "image://*/view and image://*/metadata resources."
        ),
        icons=[
            Icon(
                src=_LUCIDE.format("gallery-thumbnails"),
                mimeType="image/svg+xml",
            )
        ],
    )
    async def image_list(
        service: ImageService = Depends(get_service),
    ) -> str:
        """List all registered images with their IDs and resource URIs.

        Includes both completed images and in-progress (fire-and-forget)
        generations with their current status.

        Returns:
            JSON array of image records with resource URIs.
        """
        images = service.list_images()
        result: list[dict[str, object]] = [
            {
                "image_id": img.id,
                "status": "completed",
                "provider": img.provider,
                "content_type": img.content_type,
                "original_dimensions": list(img.original_dimensions),
                "original_uri": f"image://{img.id}/view",
                "metadata_uri": f"image://{img.id}/metadata",
                "resource_template": (
                    f"image://{img.id}/view{{?format,width,height,quality}}"
                ),
                "prompt": img.prompt,
                "created_at": datetime.fromtimestamp(
                    img.created_at, tz=UTC
                ).isoformat(),
            }
            for img in images
        ]

        # Include in-progress and failed generations
        for pending in service.list_pending():
            result.append(
                {
                    "image_id": pending.id,
                    "status": pending.status,
                    "provider": pending.provider,
                    "prompt": pending.prompt,
                    "progress": pending.progress,
                    "progress_message": pending.progress_message,
                    "original_uri": f"image://{pending.id}/view",
                    "resource_template": (
                        f"image://{pending.id}/view{{?format,width,height,quality}}"
                    ),
                    "created_at": datetime.fromtimestamp(
                        pending.created_at, tz=UTC
                    ).isoformat(),
                }
            )

        return json.dumps(result, indent=2)

    # -- MCP Apps: image viewer -------------------------------------------------

    @mcp.resource(
        _IMAGE_VIEWER_URI,
        description="Interactive image viewer for show_image results.",
        app=AppConfig(
            domain="https://image-gen-mcp.local",
            csp=ResourceCSP(resourceDomains=["https://unpkg.com"]),
        ),
    )
    def image_viewer() -> str:
        """HTML viewer that renders images from show_image tool results.

        Loaded by MCP Apps-capable clients (Claude Desktop, claude.ai) in a
        sandboxed iframe.  Listens for tool results via the ext-apps SDK and
        displays the image with metadata.
        """
        return _IMAGE_VIEWER_HTML
