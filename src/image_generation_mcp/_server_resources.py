"""MCP resource registrations.

Exposes provider capabilities, image assets, metadata, and the MCP Apps
image viewer as MCP resources.
"""

from __future__ import annotations

import io
import json
import logging
from datetime import UTC, datetime

from fastmcp import FastMCP
from fastmcp.dependencies import Depends
from fastmcp.resources import ResourceContent, ResourceResult
from fastmcp.server.apps import AppConfig, ResourceCSP
from mcp.types import Icon
from PIL import Image as PILImage

from image_generation_mcp._server_deps import get_service
from image_generation_mcp.processing import (
    convert_format,
    crop_to_dimensions,
    resize_image,
)
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
    @media (prefers-color-scheme: dark) {
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
  </div>
  <script type="module">
    import { App } from
      "https://unpkg.com/@modelcontextprotocol/ext-apps@0.4.0/app-with-deps";

    const app = new App({ name: "Image Viewer", version: "1.0.0" });

    app.ontoolresult = ({ content }) => {
      const img = content?.find(c => c.type === "image");
      const text = content?.find(c => c.type === "text");

      if (img) {
        const imgEl = document.getElementById("image");
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
          if (meta.provider) parts.push(`Provider: ${meta.provider}`);
          if (meta.dimensions) parts.push(`${meta.dimensions[0]}\u00d7${meta.dimensions[1]}`);
          if (meta.original_size_bytes) {
            const kb = (meta.original_size_bytes / 1024).toFixed(1);
            parts.push(`${kb} KB`);
          }
          document.getElementById("meta").textContent =
            (meta.prompt ? `"${meta.prompt}"\\n` : "") +
            parts.join(" \\u00b7 ");
        } catch (e) { console.warn("Image viewer: failed to parse metadata", e); }
      }
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
        record = service.get_image(image_id)
        data = record.original_path.read_bytes()
        content_type = record.content_type

        # Apply resize/crop first (always from original to prevent quality
        # degradation — see ADR-0006)
        if width > 0 and height > 0:
            data = crop_to_dimensions(data, width, height)
        elif width > 0:
            # Proportional resize by width
            img = PILImage.open(io.BytesIO(data))
            ratio = width / img.width
            new_height = round(img.height * ratio)
            data = resize_image(data, width, new_height)
        elif height > 0:
            # Proportional resize by height
            img = PILImage.open(io.BytesIO(data))
            ratio = height / img.height
            new_width = round(img.width * ratio)
            data = resize_image(data, new_width, height)

        # Apply format conversion last (one encode from spatial result)
        if format:
            data, content_type = convert_format(data, format, quality=quality)

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

        Returns:
            JSON array of image records with resource URIs.
        """
        images = service.list_images()
        result = [
            {
                "image_id": img.id,
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
        return json.dumps(result, indent=2)

    # -- MCP Apps: image viewer -------------------------------------------------

    @mcp.resource(
        _IMAGE_VIEWER_URI,
        description="Interactive image viewer for generate_image results.",
        app=AppConfig(
            csp=ResourceCSP(resourceDomains=["https://unpkg.com"]),
        ),
    )
    def image_viewer() -> str:
        """HTML viewer that renders images from generate_image tool results.

        Loaded by MCP Apps-capable clients (Claude Desktop, claude.ai) in a
        sandboxed iframe.  Listens for tool results via the ext-apps SDK and
        displays the image with metadata.
        """
        return _IMAGE_VIEWER_HTML
