"""MCP tool registrations for image generation.

Exposes ``generate_image``, ``get_image``, ``list_images``, and
``list_providers`` tools to MCP clients.
``generate_image`` is tagged ``write`` (hidden in read-only mode).
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
from datetime import UTC, datetime

from fastmcp import FastMCP
from fastmcp.dependencies import CurrentContext, Depends
from fastmcp.server.context import Context
from fastmcp.tools import ToolResult
from mcp.types import Icon, ImageContent, TextContent
from PIL import Image as PILImage

from ._server_deps import get_service
from .processing import (
    convert_format,
    crop_to_dimensions,
    generate_thumbnail,
    resize_image,
)
from .providers.types import (
    SUPPORTED_ASPECT_RATIOS,
    SUPPORTED_BACKGROUNDS,
    SUPPORTED_QUALITY_LEVELS,
    ImageContentPolicyError,
    ImageProviderConnectionError,
)
from .service import ImageService

logger = logging.getLogger(__name__)

_LUCIDE = "https://unpkg.com/lucide-static/icons/{}.svg"


def register_tools(mcp: FastMCP) -> None:
    """Register all MCP tools on *mcp*.

    Args:
        mcp: The :class:`~fastmcp.FastMCP` instance to register tools on.
    """

    @mcp.tool(
        tags={"write"},
        task=True,
        icons=[Icon(src=_LUCIDE.format("image-plus"), mimeType="image/svg+xml")],
    )
    async def generate_image(
        prompt: str,
        provider: str = "auto",
        negative_prompt: str | None = None,
        aspect_ratio: str = "1:1",
        quality: str = "standard",
        background: str = "opaque",
        service: ImageService = Depends(get_service),
        ctx: Context = CurrentContext(),
    ) -> ToolResult:
        """Generate an image and return a thumbnail preview with resource URIs.

        Call list_providers first to see available providers. Returns an
        inline thumbnail plus URIs for full-resolution access and
        on-demand transforms (resize, crop, format conversion).

        Args:
            prompt: Text description of the desired image.
            provider: Which provider to use. ``"auto"`` (default) selects
                based on prompt analysis. ``"openai"`` — best for text,
                logos, and general-purpose. ``"a1111"`` — best for
                photorealism, portraits, and artistic styles.
                ``"placeholder"`` — instant zero-cost solid-color PNG
                for testing.
            negative_prompt: Things to avoid in the image. A1111 supports
                this natively via CLIP. OpenAI appends as an "Avoid:"
                clause (weaker effect). Placeholder ignores it.
            aspect_ratio: Desired ratio (``1:1``, ``16:9``, ``9:16``,
                ``3:2``, ``2:3``).
            quality: Quality level. ``"hd"`` vs ``"standard"`` only
                affects OpenAI (gpt-image-1 maps both to its highest
                tier). A1111 and placeholder ignore this parameter.
            background: Background transparency. ``"opaque"`` (default)
                generates a solid background. ``"transparent"`` requests
                an image with a transparent background. Only supported
                by some providers (OpenAI gpt-image-1, placeholder).
                A1111 and dall-e-3 ignore this parameter.

        Returns:
            A thumbnail preview plus resource URIs for full-resolution
            access and on-demand transforms.
        """
        if aspect_ratio not in SUPPORTED_ASPECT_RATIOS:
            msg = (
                f"Unsupported aspect_ratio '{aspect_ratio}'. "
                f"Supported: {list(SUPPORTED_ASPECT_RATIOS)}"
            )
            raise ValueError(msg)
        if quality not in SUPPORTED_QUALITY_LEVELS:
            msg = (
                f"Unsupported quality '{quality}'. "
                f"Supported: {list(SUPPORTED_QUALITY_LEVELS)}"
            )
            raise ValueError(msg)
        if background not in SUPPORTED_BACKGROUNDS:
            msg = (
                f"Unsupported background '{background}'. "
                f"Supported: {', '.join(SUPPORTED_BACKGROUNDS)}"
            )
            raise ValueError(msg)

        await ctx.report_progress(0, 2, "Generating image")
        try:
            provider_name, result = await service.generate(
                prompt,
                provider=provider,
                negative_prompt=negative_prompt,
                aspect_ratio=aspect_ratio,
                quality=quality,
                background=background,
            )
        except ImageContentPolicyError as e:
            raise ImageContentPolicyError(
                e.provider,
                "Content policy rejected the prompt. "
                "Try rephrasing or use a different provider.",
            ) from None
        except ImageProviderConnectionError as e:
            raise ImageProviderConnectionError(
                e.provider,
                "Provider is unreachable. Check that it is running, "
                "or try a different provider.",
            ) from None

        await ctx.report_progress(1, 2, "Saving to scratch")

        # Register in the image registry (blocking I/O -> offload)
        record = await asyncio.to_thread(
            service.register_image,
            result,
            provider_name,
            prompt=prompt,
            negative_prompt=negative_prompt,
            aspect_ratio=aspect_ratio,
            quality=quality,
            background=background,
        )

        # Generate thumbnail (blocking Pillow -> offload)
        thumb_data, thumb_mime = await asyncio.to_thread(
            generate_thumbnail, result.image_data
        )
        thumb_b64 = base64.b64encode(thumb_data).decode("ascii")

        # Build metadata with resource URIs
        metadata = {
            "image_id": record.id,
            "original_uri": f"image://{record.id}/view",
            "metadata_uri": f"image://{record.id}/metadata",
            "resource_template": (
                f"image://{record.id}/view{{?format,width,height,quality}}"
            ),
            "original_size_bytes": result.size_bytes,
            "thumbnail_size_bytes": len(thumb_data),
            "provider": provider_name,
            "file_path": str(record.original_path),
            **result.provider_metadata,
        }

        await ctx.report_progress(2, 2, "Done")

        return ToolResult(
            content=[
                ImageContent(
                    type="image",
                    data=thumb_b64,
                    mimeType=thumb_mime,
                ),
                TextContent(
                    type="text",
                    text=json.dumps(metadata, indent=2),
                ),
            ]
        )

    @mcp.tool(
        icons=[Icon(src=_LUCIDE.format("layers"), mimeType="image/svg+xml")],
    )
    async def list_providers(
        service: ImageService = Depends(get_service),
    ) -> str:
        """List available image generation providers.

        Returns:
            JSON object with provider names and availability info.
        """
        providers = service.list_providers()
        return json.dumps(providers, indent=2)

    @mcp.tool(
        icons=[Icon(src=_LUCIDE.format("scan-eye"), mimeType="image/svg+xml")],
    )
    async def get_image(
        image_id: str,
        format: str = "",
        width: int = 0,
        height: int = 0,
        quality: int = 90,
        service: ImageService = Depends(get_service),
    ) -> ToolResult:
        """Retrieve a previously generated image by its ID.

        Use after generate_image or list_images to fetch the full-resolution
        image. Supports optional on-the-fly transforms (resize, crop, format
        conversion).

        Args:
            image_id: Image ID returned by generate_image or list_images.
            format: Convert to this format (``png``, ``webp``, ``jpeg``).
                Empty string returns the original format.
            width: Target width in pixels. 0 keeps original.
            height: Target height in pixels. 0 keeps original.
                Both width and height set: center-crop to exact dimensions.
                Only one set: proportional resize.
            quality: Compression quality for lossy formats (1-100).

        Returns:
            The image as inline content plus metadata.
        """
        record = service.get_image(image_id)
        data = await asyncio.to_thread(record.original_path.read_bytes)
        content_type = record.content_type

        # Apply resize/crop
        if width > 0 and height > 0:
            data = await asyncio.to_thread(crop_to_dimensions, data, width, height)
        elif width > 0:
            img = PILImage.open(io.BytesIO(data))
            ratio = width / img.width
            new_height = round(img.height * ratio)
            data = await asyncio.to_thread(resize_image, data, width, new_height)
        elif height > 0:
            img = PILImage.open(io.BytesIO(data))
            ratio = height / img.height
            new_width = round(img.width * ratio)
            data = await asyncio.to_thread(resize_image, data, new_width, height)

        # Apply format conversion
        if format:
            data, content_type = await asyncio.to_thread(
                convert_format, data, format, quality=quality
            )

        img_b64 = base64.b64encode(data).decode("ascii")

        return ToolResult(
            content=[
                ImageContent(type="image", data=img_b64, mimeType=content_type),
                TextContent(
                    type="text",
                    text=json.dumps(
                        {
                            "image_id": record.id,
                            "content_type": content_type,
                            "size_bytes": len(data),
                            "provider": record.provider,
                            "prompt": record.prompt,
                        },
                        indent=2,
                    ),
                ),
            ]
        )

    @mcp.tool(
        icons=[
            Icon(
                src=_LUCIDE.format("gallery-thumbnails"),
                mimeType="image/svg+xml",
            )
        ],
    )
    async def list_images(
        service: ImageService = Depends(get_service),
    ) -> str:
        """List all previously generated images.

        Returns image IDs, prompts, providers, and timestamps. Use the
        returned image_id with get_image to retrieve the full image.

        Returns:
            JSON array of image records.
        """
        images = service.list_images()
        result = [
            {
                "image_id": img.id,
                "provider": img.provider,
                "content_type": img.content_type,
                "original_dimensions": list(img.original_dimensions),
                "prompt": img.prompt,
                "created_at": datetime.fromtimestamp(
                    img.created_at, tz=UTC
                ).isoformat(),
            }
            for img in images
        ]
        return json.dumps(result, indent=2)
