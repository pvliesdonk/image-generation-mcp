"""MCP resource registrations.

Exposes provider capabilities, image assets, metadata, and the MCP Apps
image viewer as MCP resources.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import UTC, datetime

from fastmcp import FastMCP
from fastmcp.dependencies import Depends
from fastmcp.resources import ResourceContent, ResourceResult
from fastmcp.server.apps import AppConfig, ResourceCSP
from mcp.types import Icon

from image_generation_mcp._server_deps import get_service
from image_generation_mcp.config import _ENV_PREFIX
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
_IMAGE_GALLERY_URI = "ui://image-gallery/view.html"

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
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="color-scheme" content="light dark">
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    html, body { overflow: hidden; background: transparent; }
    body {
      font-family: var(--font-sans, system-ui, -apple-system, sans-serif);
      color: var(--color-text-primary, #333);
    }
    .main {
      display: flex; flex-direction: column; align-items: center;
      padding: 12px; width: 100%;
    }

    /* --- State: waiting (before any tool result) --- */
    .state-waiting {
      color: var(--color-text-tertiary, #999);
      font-size: var(--font-text-sm-size, 13px);
      padding: 32px 16px; text-align: center;
    }

    /* --- State: generating (progress) --- */
    .state-generating {
      display: none; width: 100%; max-width: 480px;
      text-align: center; padding: 24px 16px;
    }
    .state-generating .spinner {
      width: 24px; height: 24px; margin: 0 auto 12px;
      border: 3px solid var(--color-border-primary, #ddd);
      border-top-color: var(--color-text-secondary, #666);
      border-radius: 50%; animation: spin 0.8s linear infinite;
    }
    @keyframes spin { to { transform: rotate(360deg); } }
    .state-generating .gen-label {
      font-size: var(--font-text-sm-size, 13px);
      font-weight: 600;
      color: var(--color-text-secondary, #666);
    }
    .state-generating .gen-detail {
      font-size: var(--font-text-xs-size, 12px);
      color: var(--color-text-tertiary, #999);
      margin-top: 4px;
    }
    .state-generating .gen-progress {
      margin-top: 8px; height: 4px;
      background: var(--color-background-tertiary, #eee);
      border-radius: var(--border-radius-full, 9999px);
      overflow: hidden;
    }
    .state-generating .gen-progress-fill {
      height: 100%; width: 0%;
      background: var(--color-text-secondary, #666);
      border-radius: var(--border-radius-full, 9999px);
      transition: width 0.3s ease;
    }

    /* --- State: failed --- */
    .state-failed {
      display: none; width: 100%; max-width: 480px;
      text-align: center; padding: 24px 16px;
    }
    .state-failed .fail-label {
      font-size: var(--font-text-sm-size, 13px);
      font-weight: 600; color: #c33;
    }
    .state-failed .fail-detail {
      font-size: var(--font-text-xs-size, 12px);
      color: var(--color-text-tertiary, #999);
      margin-top: 4px; word-break: break-word;
    }

    /* --- State: completed (image + metadata) --- */
    .state-completed {
      display: none; width: 100%; max-width: 640px;
    }
    .state-completed img {
      width: 100%; height: auto;
      border-radius: var(--border-radius-md, 8px);
      box-shadow: var(--shadow-md, 0 2px 12px rgba(0,0,0,0.12));
    }
    .meta {
      margin-top: 10px; width: 100%;
      font-size: var(--font-text-xs-size, 12px);
      color: var(--color-text-secondary, #666);
      line-height: 1.5;
      display: flex; align-items: flex-start; gap: 8px;
    }
    .meta-text { flex: 1; min-width: 0; }
    .meta-prompt {
      font-style: italic; margin-bottom: 4px;
      color: var(--color-text-primary, #333);
    }
    .meta-details {
      color: var(--color-text-tertiary, #999);
    }
    .dl-btn {
      display: none; flex-shrink: 0;
      background: none; border: none; cursor: pointer;
      color: var(--color-text-tertiary, #999);
      padding: 2px; margin-top: -2px;
      border-radius: var(--border-radius-sm, 4px);
      transition: color 0.15s;
    }
    .dl-btn:hover { color: var(--color-text-primary, #333); }
    .dl-btn svg { width: 18px; height: 18px; display: block; }

    /* --- Cancelled --- */
    .state-cancelled {
      display: none; width: 100%; max-width: 480px;
      text-align: center; padding: 24px 16px;
      font-size: var(--font-text-sm-size, 13px);
      color: var(--color-text-tertiary, #999);
    }
  </style>
</head>
<body>
  <div class="main">
    <div class="state-waiting" id="waiting">Waiting for image&hellip;</div>
    <div class="state-generating" id="generating">
      <div class="spinner"></div>
      <div class="gen-label" id="gen-label">Generating&hellip;</div>
      <div class="gen-detail" id="gen-detail"></div>
      <div class="gen-progress"><div class="gen-progress-fill" id="gen-fill"></div></div>
    </div>
    <div class="state-failed" id="failed">
      <div class="fail-label">Generation failed</div>
      <div class="fail-detail" id="fail-detail"></div>
    </div>
    <div class="state-cancelled" id="cancelled">Cancelled</div>
    <div class="state-completed" id="completed">
      <img id="image" alt="Generated image">
      <div class="meta">
        <div class="meta-text">
          <div class="meta-prompt" id="meta-prompt"></div>
          <div class="meta-details" id="meta-details"></div>
        </div>
        <button class="dl-btn" id="dl-btn" title="Download full-resolution image">
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
            stroke="currentColor" stroke-width="2" stroke-linecap="round"
            stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
            <polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
        </button>
      </div>
    </div>
  </div>

  <script type="module">
    import { App, applyDocumentTheme, applyHostStyleVariables, applyHostFonts }
      from "https://unpkg.com/@modelcontextprotocol/ext-apps@0.4.0/app-with-deps";

    const app = new App({ name: "Image Viewer", version: "2.0.0" });

    // --- DOM refs ---
    const mainEl = document.querySelector(".main");
    const sections = {
      waiting:    document.getElementById("waiting"),
      generating: document.getElementById("generating"),
      failed:     document.getElementById("failed"),
      cancelled:  document.getElementById("cancelled"),
      completed:  document.getElementById("completed"),
    };

    // --- State management ---
    let imageKey = null;
    let currentMeta = null;   // metadata for download
    const STORE = "imgview:";
    const MAX_ENTRIES = 5;

    function show(state) {
      for (const [k, el] of Object.entries(sections)) {
        el.style.display = k === state ? "block" : "none";
      }
    }

    function extractImageKey(uri) {
      if (!uri) return null;
      const m = uri.match(/^image:\\/\\/([^/?]+)/);
      return m ? m[1] : null;
    }

    // --- localStorage cache (LRU, quota-safe) ---
    function storeKeys() {
      const keys = [];
      for (let i = 0; i < localStorage.length; i++) {
        const k = localStorage.key(i);
        if (k && k.startsWith(STORE)) keys.push(k);
      }
      return keys;
    }

    // Returns store keys sorted oldest-first by timestamp for correct LRU eviction.
    // localStorage.key(i) has no guaranteed iteration order, so we read the stored ts field.
    function storeKeysByAge() {
      return storeKeys().map(k => {
        try {
          const d = JSON.parse(localStorage.getItem(k));
          return { k, ts: (d && d.ts) ? d.ts : 0 };
        } catch (_) { return { k, ts: 0 }; }
      }).sort((a, b) => a.ts - b.ts).map(e => e.k);
    }

    function saveState(key, img, text) {
      if (!key) return;
      const fullKey = STORE + key;
      const value = JSON.stringify({ img, text, ts: Date.now() });
      try {
        localStorage.setItem(fullKey, value);
      } catch (e) {
        const keys = storeKeysByAge().filter(k => k !== fullKey);
        while (keys.length > 0) {
          localStorage.removeItem(keys.shift());
          try { localStorage.setItem(fullKey, value); return; } catch (_) {}
        }
        console.warn('localStorage full — could not save state after eviction');
        return;
      }
      const all = storeKeysByAge().filter(k => k !== fullKey);
      while (all.length >= MAX_ENTRIES) localStorage.removeItem(all.shift());
    }

    function loadState(key) {
      if (!key) return null;
      try {
        const raw = localStorage.getItem(STORE + key);
        return raw ? JSON.parse(raw) : null;
      } catch (e) { return null; }
    }

    // --- Rendering ---
    function renderGenerating(meta) {
      show("generating");
      const elapsed = meta.elapsed_seconds
        ? ` (${Math.round(meta.elapsed_seconds)}s)` : "";
      document.getElementById("gen-label").textContent =
        "Generating" + elapsed;
      const parts = [];
      if (meta.provider) parts.push(meta.provider);
      if (meta.progress_message) parts.push(meta.progress_message);
      else if (meta.prompt) parts.push("\\u201c" + meta.prompt + "\\u201d");
      document.getElementById("gen-detail").textContent =
        parts.join(" \\u00b7 ");
      const pct = (meta.progress || 0) * 100;
      document.getElementById("gen-fill").style.width =
        pct > 0 ? pct + "%" : "0%";
    }

    function renderFailed(meta) {
      show("failed");
      document.getElementById("fail-detail").textContent =
        meta.error || "Unknown error";
    }

    function renderCompleted(img, text) {
      show("completed");
      const imgEl = document.getElementById("image");
      if (img) {
        const allowed = ["image/png","image/jpeg","image/webp","image/gif"];
        const mime = allowed.includes(img.mimeType) ? img.mimeType : "image/png";
        imgEl.src = "data:" + mime + ";base64," + img.data;
      }
      if (text) {
        try {
          const m = JSON.parse(text.text);
          currentMeta = m;
          if (m.prompt) {
            imgEl.alt = m.prompt;
            document.getElementById("meta-prompt").textContent =
              "\\u201c" + m.prompt + "\\u201d";
          }
          const parts = [];
          if (m.provider) {
            let s = m.provider;
            if (m.model) s += " (" + m.model + ")";
            parts.push(s);
          }
          if (m.dimensions)
            parts.push(m.dimensions[0] + "\\u00d7" + m.dimensions[1]);
          if (m.original_size_bytes) {
            const kb = (m.original_size_bytes / 1024).toFixed(1);
            parts.push(kb + " KB");
          }
          document.getElementById("meta-details").textContent =
            parts.join(" \\u00b7 ");
          // In openLink mode, only show button when download_url exists
          if (dlMode === "openLink") {
            dlBtn.style.display = m.download_url ? "block" : "none";
          }
        } catch (e) { console.warn("Failed to parse metadata", e); }
      }
    }

    // --- Handlers (registered BEFORE connect) ---
    app.ontoolinput = (params) => {
      imageKey = extractImageKey(params?.arguments?.uri);
      // Restore cached image while waiting for result
      if (imageKey) {
        const saved = loadState(imageKey);
        if (saved) {
          renderCompleted(saved.img, saved.text);
          return;
        }
      }
      show("waiting");
    };

    app.ontoolresult = ({ content }) => {
      const img = content?.find(c => c.type === "image");
      const text = content?.find(c => c.type === "text");

      // Status-only results (generating / failed)
      if (!img && text) {
        try {
          const meta = JSON.parse(text.text);
          if (meta.status === "generating") { renderGenerating(meta); return; }
          if (meta.status === "failed") { renderFailed(meta); return; }
        } catch (e) { /* not status JSON */ }
      }

      // Completed image
      renderCompleted(img, text);
      let key = imageKey;
      if (!key && text) {
        try { key = JSON.parse(text.text).image_id; } catch (e) { console.warn('Could not parse image_id from result text', e); }
      }
      if (key) saveState(key, img, text);
    };

    app.ontoolcancelled = (params) => {
      document.getElementById("cancelled").textContent =
        "Cancelled" + (params?.reason ? ": " + params.reason : "");
      show("cancelled");
    };

    function handleHostContext(ctx) {
      if (ctx.theme) applyDocumentTheme(ctx.theme);
      if (ctx.styles?.variables) applyHostStyleVariables(ctx.styles.variables);
      if (ctx.styles?.css?.fonts) applyHostFonts(ctx.styles.css.fonts);
      if (ctx.safeAreaInsets) {
        const { top, right, bottom, left } = ctx.safeAreaInsets;
        mainEl.style.paddingTop = top + "px";
        mainEl.style.paddingRight = right + "px";
        mainEl.style.paddingBottom = bottom + "px";
        mainEl.style.paddingLeft = left + "px";
      }
    }

    app.onhostcontextchanged = handleHostContext;
    app.onerror = console.error;

    // --- Download button ---
    const dlBtn = document.getElementById("dl-btn");
    let dlMode = null; // "downloadFile" | "openLink" | null

    async function tryDownloadFile() {
      if (!currentMeta?.image_id) return false;
      const id = currentMeta.image_id;
      const mime = currentMeta.format || "image/png";
      const ext = mime.split("/").pop() || "png";
      const { isError } = await app.downloadFile({
        contents: [{
          type: "resource_link",
          uri: "image://" + id + "/view",
          name: id + "." + ext,
          mimeType: mime,
        }],
      });
      return !isError;
    }

    async function tryOpenLink() {
      if (!currentMeta?.download_url) return false;
      const { isError } = await app.openLink({ url: currentMeta.download_url });
      return !isError;
    }

    dlBtn.addEventListener("click", async () => {
      if (!currentMeta) return;
      try {
        // Try downloadFile first (full-res via MCP), fall back to openLink
        if (dlMode === "downloadFile") {
          if (await tryDownloadFile()) return;
          if (await tryOpenLink()) return;
        } else {
          if (await tryOpenLink()) return;
        }
      } catch (e) { console.warn("Download failed", e); }
    });

    await app.connect();
    const ctx = app.getHostContext();
    if (ctx) handleHostContext(ctx);

    // Show download button: prefer downloadFile, fall back to openLink
    const caps = app.getHostCapabilities();
    if (caps?.downloadFile) {
      dlMode = "downloadFile";
      dlBtn.style.display = "block";
    } else if (caps?.openLinks) {
      dlMode = "openLink";
      dlBtn.style.display = "block";
    }
  </script>
</body>
</html>"""

_IMAGE_GALLERY_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="color-scheme" content="light dark">
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    html, body { overflow: hidden; background: transparent; }
    body {
      font-family: var(--font-sans, system-ui, -apple-system, sans-serif);
      color: var(--color-text-primary, #333);
    }
    .main { padding: 12px; width: 100%; }
    @keyframes spin { to { transform: rotate(360deg); } }
    .spinner {
      width: 20px; height: 20px; flex-shrink: 0;
      border: 2px solid var(--color-border-primary, #ddd);
      border-top-color: var(--color-text-secondary, #666);
      border-radius: 50%; animation: spin 0.8s linear infinite;
    }

    /* Loading */
    .state-loading {
      display: flex; flex-direction: column; align-items: center;
      padding: 40px 16px; gap: 10px;
      color: var(--color-text-tertiary, #999);
      font-size: var(--font-text-sm-size, 13px);
    }

    /* Empty */
    .state-empty { display: none; text-align: center; padding: 48px 16px; }
    .empty-icon { color: var(--color-text-tertiary, #ccc); margin-bottom: 12px; }
    .empty-title {
      font-size: var(--font-text-sm-size, 13px); font-weight: 600;
      color: var(--color-text-secondary, #666);
    }
    .empty-sub {
      font-size: var(--font-text-xs-size, 12px);
      color: var(--color-text-tertiary, #999); margin-top: 4px;
    }
    .empty-sub code {
      font-family: var(--font-mono, monospace); font-size: 11px;
      background: var(--color-background-secondary, #f0f0f0);
      padding: 1px 4px; border-radius: 3px;
    }

    /* Grid */
    .state-grid { display: none; }
    .gallery-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
      gap: 6px;
    }

    /* Card */
    .card {
      position: relative; aspect-ratio: 1;
      border-radius: var(--border-radius-md, 8px);
      overflow: hidden;
      background: var(--color-background-secondary, #f0f0f0);
      cursor: pointer; user-select: none;
    }
    .card img {
      width: 100%; height: 100%; object-fit: cover;
      display: block; transition: opacity 0.15s;
    }
    .card:hover img, .card:focus-within img { opacity: 0.82; }
    .card-overlay {
      position: absolute; inset: 0;
      background: linear-gradient(to top, rgba(0,0,0,0.72) 0%, transparent 55%);
      opacity: 0; transition: opacity 0.15s;
      display: flex; flex-direction: column; justify-content: flex-end;
      padding: 6px;
    }
    .card:hover .card-overlay, .card:focus-within .card-overlay { opacity: 1; }
    .card-prompt {
      font-size: 10px; color: #fff; line-height: 1.3;
      overflow: hidden; display: -webkit-box;
      -webkit-line-clamp: 2; -webkit-box-orient: vertical;
      margin-bottom: 4px;
    }
    .card-footer { display: flex; align-items: center; justify-content: space-between; }
    .card-provider {
      font-size: 9px; font-weight: 600; color: rgba(255,255,255,0.85);
      background: rgba(0,0,0,0.35); padding: 1px 4px; border-radius: 3px;
      max-width: 70%; overflow: hidden; white-space: nowrap; text-overflow: ellipsis;
    }
    .card-dl {
      display: none; background: none; border: none; cursor: pointer;
      color: rgba(255,255,255,0.9); padding: 2px; line-height: 0;
    }
    .card-dl:hover { color: #fff; }
    .card-dl svg { width: 13px; height: 13px; }

    /* Pending card */
    .card-pending {
      position: absolute; inset: 0;
      display: flex; flex-direction: column; align-items: center; justify-content: center;
      gap: 6px; padding: 8px;
    }
    .card-pending .spinner { width: 18px; height: 18px; }
    .card-pending-label {
      font-size: 10px; color: var(--color-text-tertiary, #999);
      text-align: center; overflow: hidden; display: -webkit-box;
      -webkit-line-clamp: 2; -webkit-box-orient: vertical;
    }

    /* Pagination */
    .pagination {
      display: flex; align-items: center; justify-content: center;
      gap: 10px; margin-top: 10px; padding-top: 4px;
    }
    .page-btn {
      background: var(--color-background-secondary, #f0f0f0);
      border: 1px solid var(--color-border-primary, #ddd);
      border-radius: var(--border-radius-sm, 4px);
      padding: 4px 12px;
      font-size: var(--font-text-xs-size, 12px);
      cursor: pointer; color: var(--color-text-primary, #333);
    }
    .page-btn:disabled { opacity: 0.35; cursor: default; }
    .page-btn:not(:disabled):hover {
      background: var(--color-background-tertiary, #e8e8e8);
    }
    .page-info {
      font-size: var(--font-text-xs-size, 12px);
      color: var(--color-text-secondary, #666);
      min-width: 90px; text-align: center;
    }
  </style>
</head>
<body>
  <div class="main" id="main">
    <div class="state-loading" id="loading">
      <div class="spinner"></div>Loading gallery\u2026
    </div>
    <div class="state-empty" id="empty">
      <div class="empty-icon">
        <svg xmlns="http://www.w3.org/2000/svg" width="36" height="36" viewBox="0 0 24 24"
          fill="none" stroke="currentColor" stroke-width="1.5"
          stroke-linecap="round" stroke-linejoin="round">
          <rect x="3" y="3" width="18" height="18" rx="2"/>
          <circle cx="8.5" cy="8.5" r="1.5"/>
          <polyline points="21 15 16 10 5 21"/>
        </svg>
      </div>
      <div class="empty-title">No images yet</div>
      <div class="empty-sub">Use <code>generate_image</code> to create your first image.</div>
    </div>
    <div class="state-grid" id="grid-container">
      <div class="gallery-grid" id="gallery-grid"></div>
      <div class="pagination" id="pagination"></div>
    </div>
  </div>

  <script type="module">
    import { App, applyDocumentTheme, applyHostStyleVariables, applyHostFonts }
      from "https://unpkg.com/@modelcontextprotocol/ext-apps@0.4.0/app-with-deps";

    const app = new App({ name: "Image Gallery", version: "1.0.0" });

    const mainEl    = document.getElementById("main");
    const loadingEl = document.getElementById("loading");
    const emptyEl   = document.getElementById("empty");
    const gridEl    = document.getElementById("grid-container");
    const gridItems = document.getElementById("gallery-grid");
    const pagEl     = document.getElementById("pagination");

    let currentPage = 1;
    let currentTotal = 0;
    let currentPageSize = 12;
    let dlMode = null; // "downloadFile" | "openLink" | null

    // --- Helpers ---
    function trunc(s, n) {
      s = String(s || "");
      return s.length > n ? s.slice(0, n) + "\\u2026" : s;
    }
    function computePageSize() {
      const w = gridItems.offsetWidth || 300;
      const cols = Math.max(3, Math.floor(w / 160));
      return cols * 3;
    }

    // --- Display states ---
    function show(which) {
      loadingEl.style.display = which === "loading" ? "flex" : "none";
      emptyEl.style.display   = which === "empty"   ? "block" : "none";
      gridEl.style.display    = which === "grid"    ? "block" : "none";
    }

    // --- Card builder ---
    function makeCard(item) {
      const card = document.createElement("div");
      card.className = "card";
      card.tabIndex = 0;

      if (item.status === "generating" || !item.thumbnail_b64) {
        const pend = document.createElement("div");
        pend.className = "card-pending";
        const sp = document.createElement("div");
        sp.className = "spinner";
        const lbl = document.createElement("div");
        lbl.className = "card-pending-label";
        lbl.textContent = item.progress_message
          || (item.prompt ? "\\u201c" + trunc(item.prompt, 40) + "\\u201d" : "Generating\\u2026");
        pend.appendChild(sp);
        pend.appendChild(lbl);
        card.appendChild(pend);
        return card;
      }

      const img = document.createElement("img");
      img.src = "data:image/webp;base64," + item.thumbnail_b64;
      img.alt = item.prompt || "Generated image";
      img.loading = "lazy";
      card.appendChild(img);

      const overlay = document.createElement("div");
      overlay.className = "card-overlay";

      const promptDiv = document.createElement("div");
      promptDiv.className = "card-prompt";
      promptDiv.textContent = item.prompt || "";
      overlay.appendChild(promptDiv);

      const footer = document.createElement("div");
      footer.className = "card-footer";

      const badge = document.createElement("span");
      badge.className = "card-provider";
      badge.textContent = item.provider || "";
      footer.appendChild(badge);

      const dlBtn = document.createElement("button");
      dlBtn.className = "card-dl";
      dlBtn.title = "Download";
      dlBtn.dataset.imageId = item.image_id;
      dlBtn.dataset.mime = item.content_type || "image/png";
      if (item.download_url) dlBtn.dataset.downloadUrl = item.download_url;
      dlBtn.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>';
      if (dlMode === "downloadFile" || dlMode === "openLink") dlBtn.style.display = "block";
      footer.appendChild(dlBtn);

      overlay.appendChild(footer);
      card.appendChild(overlay);
      return card;
    }

    // --- Grid render ---
    function renderGrid(data) {
      const { total, items } = data;
      currentTotal = total;
      gridItems.innerHTML = "";

      if (!items || items.length === 0) {
        if (total === 0) { show("empty"); return; }
        show("grid");
        renderPagination();
        return;
      }

      show("grid");
      for (const item of items) {
        gridItems.appendChild(makeCard(item));
      }
      renderPagination();
    }

    function renderPagination() {
      const totalPages = Math.max(1, Math.ceil(currentTotal / currentPageSize));
      pagEl.innerHTML = "";
      if (totalPages <= 1) return;

      const prev = document.createElement("button");
      prev.className = "page-btn";
      prev.textContent = "\\u2190 Prev";
      prev.disabled = currentPage <= 1;
      prev.addEventListener("click", () => goTo(currentPage - 1));

      const info = document.createElement("span");
      info.className = "page-info";
      info.textContent = "Page " + currentPage + " of " + totalPages;

      const next = document.createElement("button");
      next.className = "page-btn";
      next.textContent = "Next \\u2192";
      next.disabled = currentPage >= totalPages;
      next.addEventListener("click", () => goTo(currentPage + 1));

      pagEl.append(prev, info, next);
    }

    // --- Paginate via app-only tool ---
    async function goTo(page) {
      const ps = computePageSize();
      currentPageSize = ps;
      show("loading");
      try {
        const result = await app.callServerTool("gallery_page", { page, page_size: ps });
        if (result.isError) { show("empty"); return; }
        const text = result.content?.find(c => c.type === "text")?.text;
        if (!text) { show("empty"); return; }
        const data = JSON.parse(text);
        currentPage = data.page;
        currentTotal = data.total;
        currentPageSize = data.page_size;
        renderGrid(data);
      } catch (e) {
        console.warn("gallery_page failed", e);
        show("empty");
      }
    }

    // --- Download ---
    gridItems.addEventListener("click", async (e) => {
      const btn = e.target.closest(".card-dl");
      if (!btn || !dlMode) return;
      e.stopPropagation();
      const id   = btn.dataset.imageId;
      const mime = btn.dataset.mime || "image/png";
      if (!id) return;
      const ext = mime.split("/").pop() || "png";
      try {
        if (dlMode === "downloadFile") {
          await app.downloadFile({
            contents: [{
              type: "resource_link",
              uri: "image://" + id + "/view",
              name: id + "." + ext,
              mimeType: mime,
            }],
          });
        }
      } catch (ex) { console.warn("Download failed", ex); }
    });

    // --- Lifecycle handlers (ALL before connect) ---
    app.ontoolinput = () => { show("loading"); };

    app.ontoolresult = ({ content }) => {
      const text = content?.find(c => c.type === "text");
      if (!text) { show("empty"); return; }
      try {
        const data = JSON.parse(text.text);
        if (typeof data.total !== "number") { show("empty"); return; }
        currentPage = data.page || 1;
        currentTotal = data.total;
        currentPageSize = data.page_size || 12;
        renderGrid(data);
      } catch (e) {
        console.warn("Failed to parse gallery data", e);
        show("empty");
      }
    };

    function handleHostContext(ctx) {
      if (ctx.theme) applyDocumentTheme(ctx.theme);
      if (ctx.styles?.variables) applyHostStyleVariables(ctx.styles.variables);
      if (ctx.styles?.css?.fonts) applyHostFonts(ctx.styles.css.fonts);
      if (ctx.safeAreaInsets) {
        const { top, right, bottom, left } = ctx.safeAreaInsets;
        mainEl.style.paddingTop    = (12 + top)    + "px";
        mainEl.style.paddingRight  = (12 + right)  + "px";
        mainEl.style.paddingBottom = (12 + bottom) + "px";
        mainEl.style.paddingLeft   = (12 + left)   + "px";
      }
    }

    app.onhostcontextchanged = handleHostContext;
    app.onerror = console.error;

    await app.connect();
    const ctx = app.getHostContext();
    if (ctx) handleHostContext(ctx);

    // Show download buttons only when downloadFile is available.
    // openLink fallback omitted: download_url is not returned in tool responses.
    const caps = app.getHostCapabilities();
    if (caps?.downloadFile) {
      dlMode = "downloadFile";
      document.querySelectorAll(".card-dl").forEach(b => b.style.display = "block");
    }
  </script>
</body>
</html>"""


def _compute_claude_app_domain() -> str | None:
    """Auto-compute Claude's MCP Apps sandbox domain from BASE_URL.

    Claude requires ``{sha256_prefix}.claudemcpcontent.com`` where the hash
    is derived from the full MCP endpoint URL the client connects to.

    Returns:
        The computed domain string, or ``None`` when ``BASE_URL`` is not set
        (e.g. stdio transport or local development).
    """
    base_url = os.environ.get(f"{_ENV_PREFIX}_BASE_URL", "").strip().rstrip("/")
    if not base_url:
        return None
    http_path = os.environ.get(f"{_ENV_PREFIX}_HTTP_PATH", "/mcp").strip() or "/mcp"
    if not http_path.startswith("/"):
        http_path = f"/{http_path}"
    if len(http_path) > 1:
        http_path = http_path.rstrip("/")
    mcp_url = f"{base_url}{http_path}"
    hash_prefix = hashlib.sha256(mcp_url.encode()).hexdigest()[:32]
    return f"{hash_prefix}.claudemcpcontent.com"


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

    # Resolve the MCP Apps sandbox domain.  Priority:
    # 1. Explicit APP_DOMAIN env var (any host format)
    # 2. Auto-computed from BASE_URL for Claude (sha256 of MCP endpoint URL)
    # 3. None — host assigns its own sandbox origin (stdio / local setups)
    app_domain: str | None = (
        os.environ.get(f"{_ENV_PREFIX}_APP_DOMAIN", "").strip()
        or _compute_claude_app_domain()
    )

    @mcp.resource(
        _IMAGE_VIEWER_URI,
        description="Interactive image viewer for show_image results.",
        app=AppConfig(
            domain=app_domain,
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

    # -- MCP Apps: image gallery ------------------------------------------------

    @mcp.resource(
        _IMAGE_GALLERY_URI,
        description="Interactive gallery for browsing all generated images.",
        app=AppConfig(
            domain=app_domain,
            csp=ResourceCSP(resourceDomains=["https://unpkg.com"]),
        ),
    )
    def image_gallery() -> str:
        """HTML gallery that renders a browsable grid of generated images.

        Loaded by MCP Apps-capable clients (Claude Desktop, claude.ai) in a
        sandboxed iframe.  Receives the first page of thumbnail data from the
        ``browse_gallery`` tool result, then paginates via the ``gallery_page``
        app-only tool.
        """
        return _IMAGE_GALLERY_HTML
