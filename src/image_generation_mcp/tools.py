"""MCP tool registrations for image generation.

Exposes ``generate_image``, ``transform_image``, ``show_image``,
``browse_gallery``, ``gallery_page``, ``gallery_full_image``,
``delete_image``, and ``list_providers`` tools to MCP clients.
``generate_image``, ``transform_image``, and ``delete_image`` are tagged
``write`` (hidden in read-only mode).  ``gallery_page`` and
``gallery_full_image`` are app-only (``visibility=["app"]``) and not shown
to the model.
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import re
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, urlparse

if TYPE_CHECKING:
    from collections.abc import Sequence

from fastmcp import FastMCP
from fastmcp.apps import AppConfig
from fastmcp.dependencies import CurrentContext, Depends
from fastmcp.server.context import Context
from fastmcp.server.elicitation import AcceptedElicitation
from fastmcp.tools import ToolResult
from mcp.types import (
    ClientCapabilities,
    ElicitationCapability,
    Icon,
    ImageContent,
    ResourceLink,
    TextContent,
)
from PIL import Image as PILImage
from pydantic import AnyUrl

from ._input_images import (
    ImageReferenceNotFound,
    InputImageTooLarge,
    InvalidInputImage,
    LocalFileInputDisabled,
    resolve_references,
)
from ._server_deps import get_config, get_service
from .config import ProjectConfig
from .domain import ImageRecord, ImageService, PendingGeneration
from .processing import (
    convert_format,
    crop_region,
    crop_to_dimensions,
    flip_image,
    generate_thumbnail,
    resize_image,
    rotate_image,
)
from .providers.types import (
    SUPPORTED_ASPECT_RATIOS,
    SUPPORTED_BACKGROUNDS,
    SUPPORTED_QUALITY_LEVELS,
    ImageContentPolicyError,
    ImageProviderConnectionError,
    ImageProviderError,
    ImageResult,
    InputImage,
)
from .resources import _IMAGE_GALLERY_URI, _IMAGE_VIEWER_URI

logger = logging.getLogger(__name__)

_LUCIDE = "https://unpkg.com/lucide-static/icons/{}.svg"
_THUMBNAIL_MAX_PX = 512
_GALLERY_THUMBNAIL_MAX_PX = 128
_GALLERY_PAGE_SIZE = 12
_BACKGROUND_TASKS: set[asyncio.Task[None]] = set()


def _any_provider_supports_image_input(service: ImageService) -> bool:
    """Return True if any discovered model supports reference-image input.

    Args:
        service: The :class:`ImageService` instance to query.

    Returns:
        ``True`` when at least one model in the discovered capabilities
        reports ``supports_image_input=True``; ``False`` otherwise.
    """
    return any(
        m.supports_image_input
        for caps in service.capabilities.values()
        for m in caps.models
    )


async def _confirm_paid_or_cancel(
    ctx: Context,
    config: ProjectConfig,
    resolved_name: str,
    model: str | None,
) -> ToolResult | None:
    """Confirm a paid provider via elicitation; return a cancel result or None.

    Returns ``None`` when generation may proceed (provider is free, the client
    lacks elicitation support, or the user accepted). Returns a cancellation
    :class:`ToolResult` when the user declined.

    Args:
        ctx: The MCP request context.
        config: The project configuration (used to check ``paid_providers``).
        resolved_name: The resolved provider name.
        model: The model override, if any (included in the elicitation prompt).

    Returns:
        ``None`` when generation may proceed, or a cancellation
        :class:`ToolResult` when the user declined.
    """
    if resolved_name not in config.paid_providers:
        return None
    try:
        supports_elicit = ctx.session.check_client_capability(
            ClientCapabilities(elicitation=ElicitationCapability())
        )
    except Exception:
        logger.debug(
            "check_client_capability failed; assuming no elicitation support",
            exc_info=True,
        )
        supports_elicit = False
    if not supports_elicit:
        return None
    elicit_result = await ctx.elicit(
        f"This will use {resolved_name}"
        f"{f' ({model})' if model else ''}"
        ", which costs money. Proceed?",
        response_type=None,
    )
    if not isinstance(elicit_result, AcceptedElicitation):
        return ToolResult(
            content=[
                TextContent(
                    type="text",
                    text=(
                        f"Image generation cancelled — {resolved_name} "
                        "was not confirmed."
                    ),
                )
            ]
        )
    return None


def _start_background_generation(
    service: ImageService,
    *,
    image_id: str,
    prompt: str,
    resolved_name: str,
    negative_prompt: str | None,
    aspect_ratio: str,
    quality: str,
    background: str,
    model: str | None,
    reference_images: Sequence[InputImage] | None = None,
    strength: float | None = None,
    mask: InputImage | None = None,
    source_image_ids: list[str] | None = None,
    label: str = "generation",
) -> None:
    """Register a pending entry and spawn the background generation task.

    Shared by ``generate_image`` (text-to-image) and ``transform_image``
    (reference-image input). ``reference_images`` and ``source_image_ids``
    are empty for plain text-to-image.

    Args:
        service: The :class:`ImageService` instance.
        image_id: Pre-allocated image ID for this generation.
        prompt: Text description of the desired image.
        resolved_name: The resolved provider name.
        negative_prompt: Things to avoid in the image, or ``None``.
        aspect_ratio: Desired aspect ratio (e.g. ``"1:1"``).
        quality: Quality level (``"standard"`` or ``"hd"``).
        background: Background transparency (``"opaque"`` or ``"transparent"``).
        model: Specific model override, or ``None``.
        reference_images: Optional reference images for image-to-image tasks.
        strength: Denoising strength (0.0-1.0) for image-to-image. Forwarded
            to the provider; only SD WebUI uses it. Has no effect without
            ``reference_images``.
        mask: Optional resolved mask image for inpainting. Only OpenAI
            gpt-image models support it; other providers raise
            :class:`ImageProviderError`. Applies to the first reference image.
        source_image_ids: Optional list of source image IDs to record as
            provenance on the resulting :class:`ImageRecord`.
        label: Short label used in log messages (e.g. ``"generation"`` or
            ``"transform"``).
    """
    service.register_pending(
        image_id=image_id,
        prompt=prompt,
        provider=resolved_name,
        negative_prompt=negative_prompt,
        aspect_ratio=aspect_ratio,
        quality=quality,
        background=background,
        model=model,
    )

    async def _run() -> None:
        try:
            pending = service.get_pending(image_id)
            if pending is None:
                logger.warning(
                    "get_pending(%s) returned None; progress updates will be lost",
                    image_id,
                )

            def _on_progress(fraction: float, message: str) -> None:
                if pending is not None:
                    pending.progress = fraction
                    pending.progress_message = message

            provider_name, result = await service.generate(
                prompt,
                provider=resolved_name,
                negative_prompt=negative_prompt,
                aspect_ratio=aspect_ratio,
                quality=quality,
                background=background,
                model=model,
                reference_images=reference_images,
                strength=strength,
                mask=mask,
                progress_callback=_on_progress,
            )
            await asyncio.to_thread(
                service.register_image,
                result,
                provider_name,
                prompt=prompt,
                negative_prompt=negative_prompt,
                aspect_ratio=aspect_ratio,
                quality=quality,
                background=background,
                image_id=image_id,
                source_image_ids=source_image_ids or [],
            )
            service.complete_pending(image_id)
            logger.info("Background %s completed: %s", label, image_id)
        except ImageContentPolicyError as exc:
            service.fail_pending(
                image_id,
                "Content policy rejected the prompt. "
                "Try rephrasing or use a different provider.",
            )
            logger.error(
                "Background %s failed (content policy): %s: %s", label, image_id, exc
            )
        except ImageProviderConnectionError as exc:
            service.fail_pending(
                image_id,
                "Provider is unreachable. "
                "Check that it is running, or try a different provider.",
            )
            logger.error(
                "Background %s failed (connection): %s: %s", label, image_id, exc
            )
        except Exception as exc:
            service.fail_pending(image_id, str(exc))
            logger.error(
                "Background %s failed: %s: %s",
                label,
                image_id,
                exc,
                exc_info=True,
            )

    task = asyncio.create_task(_run())
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)


def _build_lifecycle_warnings(
    providers: dict[str, dict[str, Any]],
) -> list[str]:
    """Return human-readable warning strings for legacy/deprecated models.

    Iterates the ``service.list_providers()`` envelope (a mapping of
    provider name to provider info dict) and emits one warning per
    configured model whose ``style_profile.lifecycle`` is not
    ``"current"``. Returns an empty list when no warnings apply, so the
    consumer schema is stable.

    Skips providers whose ``capabilities`` key is absent (discovery not
    yet run).

    Args:
        providers: The dict returned by :meth:`ImageService.list_providers`.

    Returns:
        Warning sentences sorted alphabetically. Each begins with
        ``"{provider}:{model_id}"`` for grep-friendly identification.
    """
    warnings: list[str] = []
    for provider_name, provider_info in providers.items():
        capabilities = provider_info.get("capabilities")
        if not capabilities:
            continue
        for model in capabilities.get("models", []):
            profile = model.get("style_profile")
            if not profile:
                continue
            lifecycle = profile.get("lifecycle", "current")
            if lifecycle == "current":
                continue
            note = profile.get("deprecation_note", "")
            model_id = model.get("model_id", "<unknown>")
            warning = f"{provider_name}:{model_id} — {lifecycle}."
            if note:
                warning = f"{warning} {note}"
            warnings.append(warning)
    return sorted(warnings)


def register_tools(mcp: FastMCP, *, transport: str = "stdio") -> None:
    """Register all MCP tools on *mcp*.

    Args:
        mcp: The :class:`~fastmcp.FastMCP` instance to register tools on.
        transport: The MCP transport in use.  ``create_download_link`` is
            only registered for non-stdio transports (``"sse"`` or
            ``"http"``), because stdio has no HTTP server.
    """

    @mcp.tool(
        tags={"write"},
        task=True,
        annotations={
            "readOnlyHint": False,
            "destructiveHint": False,
            "openWorldHint": True,
        },
        icons=[Icon(src=_LUCIDE.format("image-plus"), mimeType="image/svg+xml")],
    )
    async def generate_image(
        prompt: str,
        provider: str = "auto",
        negative_prompt: str | None = None,
        aspect_ratio: str = "1:1",
        quality: str = "standard",
        background: str = "opaque",
        model: str | None = None,
        service: ImageService = Depends(get_service),
        config: ProjectConfig = Depends(get_config),
        ctx: Context = CurrentContext(),
    ) -> ToolResult:
        """Generate an image in the background and return metadata.

        Returns immediately while the image generates in the background
        (typically 30-90 seconds).

        **After calling this tool:**

        1. Tell the user the image is being generated.
        2. Call ``check_generation_status(image_id)`` to wait for
           completion.  It returns ``"completed"``, ``"generating"``,
           or ``"failed"``.
        3. Only when status is ``"completed"``, call
           ``show_image(uri=original_uri)`` **once** to display the
           finished image.

        **Do NOT call show_image to poll** — it renders a heavy UI
        card each time.  Use ``check_generation_status`` instead.

        Call list_providers first to see available providers and model IDs.
        Check each model's ``prompt_style`` in list_providers to choose the
        right prompt format: ``"clip"`` models (SD 1.5/SDXL) need
        comma-separated CLIP tags; ``"natural_language"`` models (Flux,
        OpenAI) need descriptive sentences.  Flux ignores
        ``negative_prompt``.

        When picking ``model``, also consult each entry's ``style_profile``
        in ``list_providers``: ``style_hints`` describes what the model is
        good for; ``incompatible_styles`` describes what fights it;
        ``good_example`` and ``bad_example`` show the prompt grammar.  The
        top-level ``warnings`` array lists deprecated models to avoid for
        new long-lived workflows.

        Args:
            prompt: Text description of the desired image.
            provider: Which provider to use. ``"auto"`` (default) selects
                based on prompt analysis. ``"openai"`` — best for text
                rendering, logos, photorealistic still life, and
                transparent backgrounds. ``"gemini"`` — best for
                infographics, diagrams, complex illustrations, and
                visual storytelling; use ``quality="hd"`` for best
                results. ``"sd_webui"`` — best for photorealism,
                portraits, and artistic styles.
                ``"placeholder"`` — instant zero-cost solid-color PNG
                for testing.
            negative_prompt: Things to avoid in the image. SD WebUI
                supports this natively for SD 1.5/SDXL (CLIP-based) but
                NOT for Flux models. OpenAI and Gemini append as an
                "Avoid:" clause (weaker effect). Placeholder ignores it.
            aspect_ratio: Desired ratio (``1:1``, ``16:9``, ``9:16``,
                ``3:2``, ``2:3``). Gemini supports additional ratios
                (``3:4``, ``4:3``, ``4:1``, ``1:4``, etc.).
            quality: Quality level. ``"standard"`` uses default settings
                (fast, lower cost). ``"hd"`` enables higher quality:
                on **Gemini**, activates model reasoning (thinking) and
                2K resolution; on **OpenAI**, selects the ``"high"``
                quality tier. SD WebUI and placeholder ignore this.
            background: Background transparency. ``"opaque"`` (default)
                generates a solid background. ``"transparent"`` requests
                an image with a transparent background. Supported by
                gpt-image-1 and placeholder. dall-e-3 and SD WebUI
                always produce opaque images (this parameter is ignored).
            model: Specific model to use (e.g., a checkpoint name for
                SD WebUI, or ``"dall-e-3"`` for OpenAI). Use
                ``list_providers`` to see available model IDs. Defaults
                to the provider's configured model.

        Returns:
            JSON metadata with ``status``, ``image_id``, and
            ``original_uri``.  Use ``check_generation_status(image_id)``
            to wait, then ``show_image(uri=original_uri)`` once ready.
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

        # Resolve provider before generation so we can check if it's paid
        resolved_name = await asyncio.to_thread(
            service.resolve_provider_name,
            provider,
            prompt,
            background=background,
        )

        # If the resolved provider is paid and the client supports
        # elicitation, ask for confirmation before spending money.
        cancel = await _confirm_paid_or_cancel(ctx, config, resolved_name, model)
        if cancel is not None:
            return cancel

        # Pre-allocate image ID and spawn background generation task
        image_id = service.allocate_image_id()
        _start_background_generation(
            service,
            image_id=image_id,
            prompt=prompt,
            resolved_name=resolved_name,
            negative_prompt=negative_prompt,
            aspect_ratio=aspect_ratio,
            quality=quality,
            background=background,
            model=model,
        )

        # Resolve prompt_style from capabilities for the response
        prompt_style = None
        caps = service.capabilities.get(resolved_name)
        if caps:
            if model:
                for m in caps.models:
                    if m.model_id == model:
                        prompt_style = m.prompt_style
                        break
            elif len(caps.models) == 1:
                prompt_style = caps.models[0].prompt_style

        # Return immediately with pending status.  ``file_ref`` is NOT
        # published here — at this point bytes don't exist yet AND the
        # provider-chosen content_type (PNG / WebP / JPEG) is not yet known,
        # so we'd be forced to lie about ``mime_type`` at publish time.
        # Consumers poll via ``check_generation_status`` and call
        # ``show_image`` once status="completed" — show_image is the file_ref
        # publisher (it knows the actual ``record.content_type``).
        metadata: dict[str, Any] = {
            "status": "generating",
            "image_id": image_id,
            "prompt": prompt,
            "provider": resolved_name,
            "prompt_style": prompt_style,
            "original_uri": f"image://{image_id}/view",
            "metadata_uri": f"image://{image_id}/metadata",
            "resource_template": (
                f"image://{image_id}/view{{?format,width,height,quality,crop_x,crop_y,crop_w,crop_h,rotate,flip}}"
            ),
        }

        return ToolResult(
            content=[
                TextContent(
                    type="text",
                    text=json.dumps(metadata, indent=2),
                ),
                ResourceLink(
                    type="resource_link",
                    uri=AnyUrl(f"image://{image_id}/view"),
                    name="Generated image (generating)",
                ),
            ]
        )

    @mcp.tool(
        tags={"write"},
        task=True,
        annotations={
            "readOnlyHint": False,
            "destructiveHint": False,
            "openWorldHint": True,
        },
        icons=[Icon(src=_LUCIDE.format("images"), mimeType="image/svg+xml")],
    )
    async def transform_image(
        prompt: str,
        reference_images: list[str],
        provider: str = "auto",
        negative_prompt: str | None = None,
        aspect_ratio: str = "1:1",
        quality: str = "standard",
        background: str = "opaque",
        model: str | None = None,
        strength: float | None = None,
        mask: str | None = None,
        service: ImageService = Depends(get_service),
        config: ProjectConfig = Depends(get_config),
        ctx: Context = CurrentContext(),
    ) -> ToolResult:
        """Edit or transform image(s) using a model that accepts image input.

        Supply one or more reference images (gallery ``image_id``, an
        ``image://`` URI, or — when enabled — a local file path) plus a
        prompt describing the change.  Served by any provider that reports
        ``supports_image_input`` in ``list_providers``; each provider's
        ``max_input_images`` there gives its reference-image limit (some
        accept one, others up to 16 for multi-image composition).

        Optionally supply a ``mask`` image (gallery ``image_id`` or URI) for
        inpainting — the mask defines which region of the first reference image
        to repaint.  Only mask-capable providers (currently OpenAI gpt-image
        family) are routed when a mask is given.

        Returns immediately; poll ``check_generation_status(image_id)``
        and then ``show_image(uri=original_uri)`` once completed — same
        flow as ``generate_image``.

        **After calling this tool:**

        1. Tell the user the image is being transformed.
        2. Call ``check_generation_status(image_id)`` to wait for completion.
        3. Only when status is ``"completed"``, call
           ``show_image(uri=original_uri)`` once to display the result.

        Args:
            prompt: Description of the desired edit or transformation.
            reference_images: One or more gallery ``image_id`` values,
                ``image://`` URIs, or (when
                ``IMAGE_GENERATION_MCP_ALLOW_LOCAL_FILE_INPUT=true``) local
                file paths to use as the source image(s).
            provider: Provider to use, or ``"auto"`` to select
                automatically.  Image-to-image is served by any provider that
                reports ``supports_image_input`` in ``list_providers``; check
                ``max_input_images`` there for each provider's reference limit.
            negative_prompt: Things to avoid in the result (provider
                support varies).
            aspect_ratio: Desired aspect ratio of the output image.
            quality: ``"standard"`` or ``"hd"``.
            background: ``"opaque"`` or ``"transparent"``
                (provider-dependent).
            model: Specific model id; see ``list_providers``.
            strength: Denoising strength for SD WebUI img2img (0.0-1.0,
                where higher regenerates more and lower preserves the
                reference image). Used only by SD WebUI and only with a
                reference image; other providers and the text-to-image
                path ignore it.
            mask: Optional gallery ``image_id`` or ``image://`` URI of a
                mask image for inpainting. Defines which region of the
                first reference image to repaint. Only mask-capable
                providers (currently OpenAI gpt-image models) are routed
                when this is supplied; other providers raise an error.
                Applies to the first reference image.

        Returns:
            JSON with ``status``, ``image_id``, ``original_uri`` (pending).
            Use ``check_generation_status(image_id)`` to poll, then
            ``show_image(uri=original_uri)`` when completed.
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
        if not reference_images:
            raise ValueError("reference_images must not be empty.")
        if strength is not None and not 0.0 <= strength <= 1.0:
            raise ValueError(f"strength must be between 0.0 and 1.0; got {strength}.")
        if not _any_provider_supports_image_input(service):
            raise ValueError(
                "No configured provider supports reference-image input. "
                "See list_providers and the README for supported providers."
            )

        # Build a loader that maps gallery image_id → (bytes, content_type)
        def _loader(image_id: str) -> tuple[bytes, str]:
            try:
                record = service.get_image(image_id)
                return record.original_path.read_bytes(), record.content_type
            except ImageProviderError as exc:
                raise KeyError(image_id) from exc
            except OSError as exc:
                # Record exists but its backing file is gone/unreadable.
                raise KeyError(image_id) from exc

        try:
            resolved = await asyncio.to_thread(
                resolve_references,
                reference_images,
                loader=_loader,
                allow_local_files=config.allow_local_file_input,
                max_bytes=config.max_input_image_bytes,
            )
        except (
            ImageReferenceNotFound,
            LocalFileInputDisabled,
            InputImageTooLarge,
            InvalidInputImage,
        ) as exc:
            raise ValueError(str(exc)) from exc

        # Resolve mask image when provided
        resolved_mask: InputImage | None = None
        if mask is not None:
            try:
                resolved_mask = (
                    await asyncio.to_thread(
                        resolve_references,
                        [mask],
                        loader=_loader,
                        allow_local_files=config.allow_local_file_input,
                        max_bytes=config.max_input_image_bytes,
                    )
                )[0]
            except (
                ImageReferenceNotFound,
                LocalFileInputDisabled,
                InputImageTooLarge,
                InvalidInputImage,
            ) as exc:
                raise ValueError(str(exc)) from exc

        # Resolve provider name. For "auto", restrict candidates to providers
        # whose capabilities include a model that supports image input AND
        # accepts at least len(resolved) references, so auto-selection cannot
        # pick a provider that would then reject this request's reference count
        # (caps vary by model and are read from max_input_images below).
        # When a mask is given, additionally require supports_mask.
        # Prefer Gemini among the eligible providers (higher-quality edits);
        # the explicit check keeps that preference robust if a future provider
        # would otherwise sort ahead of "gemini". Else pick the first eligible
        # provider alphabetically for determinism.
        if provider == "auto":
            # The mask gate uses the original `mask` str param (not
            # resolved_mask): either being non-None means a mask was requested;
            # resolved_mask is None only when mask is None.
            eligible = sorted(
                name
                for name, caps in service.capabilities.items()
                if any(
                    m.supports_image_input
                    and m.max_input_images >= len(resolved)
                    and (mask is None or m.supports_mask)
                    for m in caps.models
                )
            )
            if not eligible:
                ref_clause = (
                    f"{len(resolved)} reference image(s) with a mask"
                    if mask is not None
                    else f"{len(resolved)} reference image(s)"
                )
                raise ValueError(
                    f"No configured provider accepts {ref_clause}. See "
                    "list_providers (max_input_images) for per-model limits."
                )
            chosen_provider = "gemini" if "gemini" in eligible else eligible[0]
        else:
            chosen_provider = provider
        resolved_name = await asyncio.to_thread(
            service.resolve_provider_name,
            chosen_provider,
            prompt,
            background=background,
        )
        # caps is always present here: resolved_name is a registered provider
        # and discover_all_capabilities populates _capabilities for every
        # registered provider (even degraded ones). The ``else ()`` is a
        # defensive fallback only.
        caps = service.capabilities.get(resolved_name)
        # Pre-flight guard, not a model selector: ``capable`` is only checked
        # for emptiness below to reject early. The provider still picks the
        # actual model at generation time.
        capable = [
            m
            for m in (caps.models if caps else ())
            if m.supports_image_input
            and (model is None or m.model_id == model)
            and m.max_input_images >= len(resolved)
            and (mask is None or m.supports_mask)
        ]
        if not capable:
            ref_clause = (
                f"{len(resolved)} reference image(s) with a mask"
                if mask is not None
                else f"{len(resolved)} reference image(s)"
            )
            raise ValueError(
                f"Provider '{resolved_name}' has no model accepting {ref_clause}. "
                "See list_providers for models supporting reference-image input."
            )

        cancel = await _confirm_paid_or_cancel(ctx, config, resolved_name, model)
        if cancel is not None:
            return cancel

        # Resolve prompt_style for the response, reusing the capability
        # lookup from the routing check above.
        prompt_style = None
        if caps:
            if model:
                for m in caps.models:
                    if m.model_id == model:
                        prompt_style = m.prompt_style
                        break
            elif len(caps.models) == 1:
                prompt_style = caps.models[0].prompt_style

        source_ids = [r.source_id for r in resolved if r.source_id]
        if resolved_mask and resolved_mask.source_id:
            source_ids.append(resolved_mask.source_id)
        image_id = service.allocate_image_id()
        _start_background_generation(
            service,
            image_id=image_id,
            prompt=prompt,
            resolved_name=resolved_name,
            negative_prompt=negative_prompt,
            aspect_ratio=aspect_ratio,
            quality=quality,
            background=background,
            model=model,
            reference_images=resolved,
            strength=strength,
            mask=resolved_mask,
            source_image_ids=source_ids,
            label="transform",
        )

        metadata: dict[str, Any] = {
            "status": "generating",
            "image_id": image_id,
            "prompt": prompt,
            "provider": resolved_name,
            "prompt_style": prompt_style,
            "source_image_ids": source_ids,
            "original_uri": f"image://{image_id}/view",
            "metadata_uri": f"image://{image_id}/metadata",
            "resource_template": (
                f"image://{image_id}/view{{?format,width,height,quality,crop_x,crop_y,crop_w,crop_h,rotate,flip}}"
            ),
        }
        return ToolResult(
            content=[
                TextContent(
                    type="text",
                    text=json.dumps(metadata, indent=2),
                ),
                ResourceLink(
                    type="resource_link",
                    uri=AnyUrl(f"image://{image_id}/view"),
                    name="Transformed image (generating)",
                ),
            ]
        )

    @mcp.tool(
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": False,
            "idempotentHint": True,
        },
    )
    async def check_generation_status(
        image_id: str,
        service: ImageService = Depends(get_service),
    ) -> str:
        """Check whether a background image generation has finished.

        Call this after ``generate_image`` to wait for completion.
        Returns a short JSON status — no image data, no heavy UI.

        - ``"completed"`` → call ``show_image(uri=original_uri)`` to
          display the finished image.
        - ``"generating"`` → wait and check again.
        - ``"failed"`` → report the error to the user.

        Args:
            image_id: The ``image_id`` returned by ``generate_image``.

        Returns:
            JSON with ``status``, ``image_id``, and optional
            ``progress``, ``progress_message``, ``elapsed_seconds``,
            or ``error``.
        """
        pending = service.get_pending(image_id)

        if pending is None:
            # No pending entry — either already completed or unknown.
            # get_image is a dict lookup (no file I/O).
            try:
                await asyncio.to_thread(service.get_image, image_id)
            except ImageProviderError:
                return json.dumps(
                    {
                        "status": "unknown",
                        "image_id": image_id,
                        "error": "No pending or completed image with this ID.",
                    }
                )
            return json.dumps({"status": "completed", "image_id": image_id})

        if pending.status == "generating":
            return json.dumps(
                {
                    "status": "generating",
                    "image_id": image_id,
                    "progress": pending.progress,
                    "progress_message": pending.progress_message,
                    "elapsed_seconds": round(time.time() - pending.created_at, 1),
                }
            )

        if pending.status == "failed":
            error = pending.error or "Unknown error"
            service.cleanup_pending(image_id)
            return json.dumps(
                {
                    "status": "failed",
                    "image_id": image_id,
                    "error": error,
                }
            )

        # completed
        service.cleanup_pending(image_id)
        return json.dumps({"status": "completed", "image_id": image_id})

    @mcp.tool(
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": False,
        },
        icons=[Icon(src=_LUCIDE.format("eye"), mimeType="image/svg+xml")],
        app=AppConfig(resource_uri=_IMAGE_VIEWER_URI),
    )
    async def show_image(
        uri: str,
        with_link: bool = True,
        service: ImageService = Depends(get_service),
        config: ProjectConfig = Depends(get_config),
    ) -> ToolResult:
        """Display a completed image with optional on-demand transforms.

        **Only call this for completed images** — use
        ``check_generation_status`` to poll, then call this once when
        ``status`` is ``"completed"``.

        Accepts a full ``image://`` resource URI (e.g.
        ``image://abc123/view`` or
        ``image://abc123/view?format=webp&width=512``).  Transforms are
        encoded in the URI query string — no separate parameters needed.

        Read the ``image://list`` resource to browse available image IDs.

        Args:
            uri: A full ``image://`` resource URI, optionally with query
                params: ``format`` (``png``, ``webp``, ``jpeg``),
                ``width`` (pixels), ``height`` (pixels),
                ``quality`` (1-100, for lossy formats).
            with_link: When ``True`` (default), include a one-time
                ``download_url`` in the metadata.  Only available on
                HTTP deployments with ``BASE_URL`` configured — absent
                on stdio transport.  If present in the response, show
                the URL to the user as a clickable link (the MCP App
                widget cannot open it from its sandboxed iframe).

        Returns:
            For completed images: a WebP thumbnail preview (max 512px,
            under 1 MB) as ``ImageContent`` plus JSON metadata.
            For in-progress images: JSON with ``status`` and progress info.
            For full-resolution access, use the ``image://`` resource URI
            or the download URL.
        """
        parsed = urlparse(uri)
        if parsed.scheme != "image":
            msg = f"Expected an image:// URI, got scheme '{parsed.scheme}'"
            raise ValueError(msg)
        image_id = parsed.netloc or ""
        qs = parse_qs(parsed.query)

        fmt = qs.get("format", [""])[0]
        width = int(qs.get("width", ["0"])[0])
        height = int(qs.get("height", ["0"])[0])
        quality = int(qs.get("quality", ["90"])[0])
        quality = max(1, min(100, quality))

        # If image is still generating or failed, redirect to the
        # lightweight polling tool instead of rendering a heavy card.
        pending = service.get_pending(image_id)
        if pending is not None and pending.status in ("generating", "failed"):
            return ToolResult(
                content=[
                    TextContent(
                        type="text",
                        text=json.dumps(
                            {
                                "status": pending.status,
                                "image_id": image_id,
                                "error": (
                                    "Image not ready. Use "
                                    "check_generation_status(image_id) to poll."
                                ),
                            },
                            indent=2,
                        ),
                    )
                ]
            )

        # Completed pending — clean up and fall through to normal display
        if pending is not None and pending.status == "completed":
            service.cleanup_pending(image_id)

        record = await asyncio.to_thread(service.get_image, image_id)
        data = await asyncio.to_thread(record.original_path.read_bytes)
        content_type = record.content_type

        # Apply resize/crop first (always from original to prevent quality
        # degradation — see ADR-0006)
        if width > 0 and height > 0:
            data = await asyncio.to_thread(crop_to_dimensions, data, width, height)
        elif width > 0:
            orig_w, orig_h = record.original_dimensions
            ratio = width / orig_w
            new_height = round(orig_h * ratio)
            data = await asyncio.to_thread(resize_image, data, width, new_height)
        elif height > 0:
            orig_w, orig_h = record.original_dimensions
            ratio = height / orig_h
            new_width = round(orig_w * ratio)
            data = await asyncio.to_thread(resize_image, data, new_width, height)

        # Apply format conversion last (one encode from spatial result)
        if fmt:
            data, content_type = await asyncio.to_thread(
                convert_format, data, fmt, quality
            )

        # Determine final dimensions — use stored metadata when no spatial
        # transform was applied to avoid an extra Pillow decode.
        transforms_changed_size = width > 0 or height > 0
        if transforms_changed_size:
            final_img = await asyncio.to_thread(lambda: PILImage.open(io.BytesIO(data)))
            final_w, final_h = final_img.size
        else:
            final_w, final_h = record.original_dimensions

        # Always cap the ImageContent to a thumbnail (max 512px, WebP,
        # quality 80) to stay under the ~1 MB tool-result size limit
        # imposed by Claude Desktop and other MCP clients.  The full-
        # resolution image remains available via the image:// resource URI.
        def _make_thumb(src: bytes) -> tuple[bytes, str, tuple[int, int]]:
            td, tm = generate_thumbnail(src, _THUMBNAIL_MAX_PX, "webp", 80)
            tw, th = PILImage.open(io.BytesIO(td)).size
            return td, tm, (tw, th)

        thumb_data, thumb_mime, thumb_dims = await asyncio.to_thread(_make_thumb, data)
        thumb_b64 = base64.b64encode(thumb_data).decode("ascii")

        transform_params: dict[str, int | str] = {}
        if fmt:
            transform_params["format"] = fmt
        if width:
            transform_params["width"] = width
        if height:
            transform_params["height"] = height
        if fmt and quality != 90:
            transform_params["quality"] = quality

        original_stat = await asyncio.to_thread(record.original_path.stat)
        metadata: dict[str, object] = {
            "image_id": record.id,
            "prompt": record.prompt,
            "provider": record.provider,
            "model": record.provider_metadata.get("model"),
            "prompt_style": record.provider_metadata.get("prompt_style"),
            "dimensions": [final_w, final_h],
            "thumbnail_dimensions": list(thumb_dims),
            "original_size_bytes": original_stat.st_size,
            "format": content_type,
            "transforms_applied": transform_params,
        }

        # Auto-generate a download link when on HTTP transport with
        # BASE_URL configured and with_link is True.
        if with_link:
            base_url = (config.server.base_url or "").rstrip("/")
            if base_url:
                from .artifacts import get_artifact_store

                try:
                    store = get_artifact_store()
                    token = store.create_token(uri, ttl_seconds=300)
                    metadata["download_url"] = f"{base_url}/artifacts/{token}"
                except RuntimeError:
                    logger.debug(
                        "artifact_store_unavailable uri=%s", uri, exc_info=True
                    )

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
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": False,
        },
        icons=[Icon(src=_LUCIDE.format("images"), mimeType="image/svg+xml")],
        app=AppConfig(resource_uri=_IMAGE_GALLERY_URI),
    )
    async def browse_gallery(
        service: ImageService = Depends(get_service),
    ) -> ToolResult:
        """Browse all generated images in an interactive visual gallery.

        Opens a gallery view showing thumbnail previews of every image in the
        scratch directory.

        For non-UI clients the response is a JSON object with ``total``,
        ``page``, ``page_size``, and ``items``.  Each completed item includes
        ``image_id``, ``prompt``, ``provider``, ``dimensions``,
        ``created_at``, ``thumbnail_b64`` (128 px WebP, base64-encoded),
        and ``content_type``.  Pending/generating items include ``status``,
        ``progress``, and ``progress_message`` instead of a thumbnail.

        Use ``browse_gallery`` to see all images; use
        ``show_image(uri="image://{image_id}/view")`` to view one
        image at full resolution.

        Returns:
            JSON with gallery data (total count, page metadata, thumbnail
            items for page 1) as a :class:`~fastmcp.tools.ToolResult`.
        """
        images = sorted(service.list_images(), key=lambda r: r.created_at, reverse=True)
        pending = sorted(
            service.list_pending(), key=lambda p: p.created_at, reverse=True
        )
        total = len(images) + len(pending)

        # Build page-1 items: pending first (newest), then completed
        page_size = _GALLERY_PAGE_SIZE
        all_items: list[dict[str, object]] = []
        for p in pending:
            if len(all_items) >= page_size:
                break
            all_items.append(
                {
                    "image_id": p.id,
                    "status": p.status,
                    "prompt": p.prompt,
                    "provider": p.provider,
                    "progress": p.progress,
                    "progress_message": p.progress_message,
                }
            )
        for img in images:
            if len(all_items) >= page_size:
                break
            img_data = await asyncio.to_thread(img.original_path.read_bytes)
            thumb_bytes, _ = await asyncio.to_thread(
                generate_thumbnail, img_data, _GALLERY_THUMBNAIL_MAX_PX, "webp", 80
            )
            all_items.append(
                {
                    "image_id": img.id,
                    "status": "completed",
                    "prompt": img.prompt,
                    "provider": img.provider,
                    "dimensions": list(img.original_dimensions),
                    "created_at": datetime.fromtimestamp(
                        img.created_at, tz=UTC
                    ).isoformat(),
                    "thumbnail_b64": base64.b64encode(thumb_bytes).decode(),
                    "content_type": img.content_type,
                }
            )

        gallery_data = {
            "total": total,
            "page": 1,
            "page_size": page_size,
            "items": all_items,
        }

        return ToolResult(
            content=[
                TextContent(
                    type="text",
                    text=json.dumps(gallery_data),
                )
            ]
        )

    @mcp.tool(
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": False,
        },
        app=AppConfig(resource_uri=_IMAGE_GALLERY_URI, visibility=["app"]),
    )
    async def gallery_page(
        page: int = 1,
        page_size: int = _GALLERY_PAGE_SIZE,
        service: ImageService = Depends(get_service),
    ) -> str:
        """Return a page of image thumbnails for the gallery UI.

        App-only helper called by the gallery UI to load additional pages when
        the user paginates.  Not intended for direct model invocation.

        Args:
            page: 1-based page number.
            page_size: Number of items per page (1-24, default 12).

        Returns:
            JSON with ``total``, ``page``, ``page_size``, and ``items``.
            Each completed item includes ``thumbnail_b64`` (128 px WebP).
            Pending/generating items omit the thumbnail.
        """
        images = sorted(service.list_images(), key=lambda r: r.created_at, reverse=True)
        pending = sorted(
            service.list_pending(), key=lambda p: p.created_at, reverse=True
        )
        total = len(images) + len(pending)

        page = max(1, page)
        page_size = max(1, min(24, page_size))
        start = (page - 1) * page_size

        # Merge pending + completed; pending items go first (newest)
        all_pending = list(pending)
        all_completed = list(images)
        all_meta: list[tuple[str, PendingGeneration | ImageRecord]] = [
            ("pending", p) for p in all_pending
        ] + [("completed", img) for img in all_completed]
        page_slice = all_meta[start : start + page_size]

        items: list[dict[str, object]] = []
        for kind, record in page_slice:
            if kind == "pending" and isinstance(record, PendingGeneration):
                items.append(
                    {
                        "image_id": record.id,
                        "status": record.status,
                        "prompt": record.prompt,
                        "provider": record.provider,
                        "progress": record.progress,
                        "progress_message": record.progress_message,
                    }
                )
            elif isinstance(record, ImageRecord):
                img_data = await asyncio.to_thread(record.original_path.read_bytes)
                thumb_bytes, _ = await asyncio.to_thread(
                    generate_thumbnail, img_data, _GALLERY_THUMBNAIL_MAX_PX, "webp", 80
                )
                items.append(
                    {
                        "image_id": record.id,
                        "status": "completed",
                        "prompt": record.prompt,
                        "provider": record.provider,
                        "dimensions": list(record.original_dimensions),
                        "created_at": datetime.fromtimestamp(
                            record.created_at, tz=UTC
                        ).isoformat(),
                        "thumbnail_b64": base64.b64encode(thumb_bytes).decode(),
                        "content_type": record.content_type,
                    }
                )

        return json.dumps(
            {"total": total, "page": page, "page_size": page_size, "items": items}
        )

    _LIGHTBOX_MAX_BYTES = 1 * 1024 * 1024  # 1 MB size cap for lightbox images
    _LIGHTBOX_MAX_PX = 1024  # resize target when image exceeds size cap

    @mcp.tool(
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": False,
        },
        app=AppConfig(resource_uri=_IMAGE_GALLERY_URI, visibility=["app"]),
    )
    async def gallery_full_image(
        image_id: str,
        service: ImageService = Depends(get_service),
    ) -> str:
        """Return full-resolution image data for the gallery lightbox.

        App-only helper called by the gallery lightbox to load a single image
        at full (or near-full) resolution.  Images larger than 1 MB are
        downscaled to 1024 px wide WebP before encoding.

        Args:
            image_id: The image ID to load.

        Returns:
            JSON with ``image_id``, ``b64``, ``content_type``, ``dimensions``,
            ``prompt``, ``provider``, and ``created_at``.
        """
        record = service.get_image(image_id)  # simple dict lookup, no I/O
        # Check file size via stat to decide transform upfront — avoids double
        # read: stat is O(1), reading bytes is O(size).
        file_size = await asyncio.to_thread(lambda: record.original_path.stat().st_size)
        if file_size > _LIGHTBOX_MAX_BYTES:
            img_bytes, content_type = await asyncio.to_thread(
                service.get_transformed_image,
                image_id,
                "webp",
                _LIGHTBOX_MAX_PX,
                0,
                85,
            )
        else:
            img_bytes, content_type = await asyncio.to_thread(
                service.get_transformed_image, image_id
            )
        return json.dumps(
            {
                "image_id": record.id,
                "b64": base64.b64encode(img_bytes).decode(),
                "content_type": content_type,
                "dimensions": list(record.original_dimensions),
                "prompt": record.prompt,
                "provider": record.provider,
                "created_at": datetime.fromtimestamp(
                    record.created_at, tz=UTC
                ).isoformat(),
            }
        )

    @mcp.tool(
        tags={"write"},
        icons=[Icon(src=_LUCIDE.format("trash-2"), mimeType="image/svg+xml")],
        annotations={
            "readOnlyHint": False,
            "destructiveHint": True,
            "openWorldHint": False,
        },
    )
    async def delete_image(
        image_id: str,
        service: ImageService = Depends(get_service),
    ) -> str:
        """Delete an image from the scratch directory.

        Permanently removes the image file and its metadata sidecar.
        This action cannot be undone.  Hidden in read-only mode.

        Args:
            image_id: The image ID to delete (12-character hex string).

        Returns:
            Confirmation text with the deleted image's prompt and provider.
        """
        record = await asyncio.to_thread(service.delete_image, image_id)
        return (
            f"Deleted image {record.id} "
            f"(prompt: {record.prompt!r}, provider: {record.provider})"
        )

    @mcp.tool(
        icons=[Icon(src=_LUCIDE.format("layers"), mimeType="image/svg+xml")],
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": True,
            "idempotentHint": False,
        },
    )
    async def list_providers(
        force_refresh: bool = False,
        service: ImageService = Depends(get_service),
    ) -> str:
        """List available image generation providers, models, and capabilities.

        Returns provider names, available models, and capability details.
        Each model includes a ``prompt_style`` field: use ``"clip"`` for
        comma-separated CLIP tags (SD 1.5/SDXL) or ``"natural_language"``
        for descriptive sentences (Flux, OpenAI).  Each call includes a
        ``refreshed_at`` timestamp.  Pass ``force_refresh=true`` if
        providers may have changed since the last check.

        Also available as the ``info://providers`` resource for clients
        that support MCP resources.

        Args:
            force_refresh: When ``True``, re-runs capability discovery on
                all registered providers before returning, updating cached
                results. Use when providers may have changed (e.g., new
                SD WebUI checkpoints loaded).

        Returns:
            JSON object with provider names, capabilities, and a
            ``refreshed_at`` ISO 8601 timestamp.
        """
        if force_refresh:
            await service.discover_all_capabilities()
        providers = service.list_providers()
        warnings = _build_lifecycle_warnings(providers)
        result = {
            "refreshed_at": datetime.now(UTC).isoformat(),
            "providers": providers,
            "warnings": warnings,
        }
        return json.dumps(result, indent=2)

    @mcp.tool(
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": False,
        },
        icons=[Icon(src=_LUCIDE.format("crop"), mimeType="image/svg+xml")],
        app=AppConfig(resource_uri=_IMAGE_VIEWER_URI),
    )
    async def edit_image(
        image_id: str,
        service: ImageService = Depends(get_service),
    ) -> ToolResult:
        """Open an image for interactive editing (crop, rotate, flip).

        The user edits in the viewer UI and saves as a new image. Always
        edits the original image — resource template transforms are
        ephemeral and LLM-facing; editor transforms are persistent and
        user-facing.

        Args:
            image_id: ID of the image to edit. Use ``image://list`` to
                browse available image IDs.

        Returns:
            Full-resolution image as base64 plus JSON metadata with
            ``editable: true`` to activate the editor UI.
        """
        record = await asyncio.to_thread(service.get_image, image_id)
        image_data = await asyncio.to_thread(record.original_path.read_bytes)
        b64 = base64.b64encode(image_data).decode()

        metadata = json.dumps(
            {
                "editable": True,
                "image_id": image_id,
                "content_type": record.content_type,
                "dimensions": list(record.original_dimensions),
                "prompt": record.prompt,
                "provider": record.provider,
            }
        )

        return ToolResult(
            content=[
                TextContent(type="text", text=metadata),
                ImageContent(
                    type="image",
                    data=b64,
                    mimeType=record.content_type,
                ),
            ]
        )

    @mcp.tool(
        tags={"write"},
        annotations={
            "readOnlyHint": False,
            "destructiveHint": False,
            "openWorldHint": False,
        },
        app=AppConfig(visibility=["app"]),
    )
    async def _save_edited_image(
        source_image_id: str,
        crop: dict[str, int] | None = None,
        rotate: int | None = None,
        flip_horizontal: bool = False,
        flip_vertical: bool = False,
        service: ImageService = Depends(get_service),
    ) -> ToolResult:
        """Save an edited image as a new first-class image record.

        Called by the image editor UI after the user confirms their edits.
        Applies the transforms server-side via Pillow and persists the
        result as a new image with ``source_image_ids`` provenance.

        Args:
            source_image_id: ID of the original image being edited.
            crop: Optional crop box as ``{"x": int, "y": int, "w": int,
                "h": int}``.
            rotate: Optional rotation in degrees — 90, 180, or 270.
            flip_horizontal: Mirror the image left-right.
            flip_vertical: Mirror the image top-bottom.

        Returns:
            JSON with the new ``image_id`` and resource URI.
        """

        def _save() -> ImageRecord:
            record = service.get_image(source_image_id)
            data = record.original_path.read_bytes()

            if crop:
                try:
                    cx, cy, cw, ch = (
                        int(crop["x"]),
                        int(crop["y"]),
                        int(crop["w"]),
                        int(crop["h"]),
                    )
                except (KeyError, TypeError, ValueError) as exc:
                    msg = f"crop must have integer keys x, y, w, h; got {crop!r}"
                    raise ValueError(msg) from exc
                data = crop_region(data, cx, cy, cw, ch)
            if rotate:
                data = rotate_image(data, int(rotate))
            if flip_horizontal:
                data = flip_image(data, "horizontal")
            if flip_vertical:
                data = flip_image(data, "vertical")

            result = ImageResult(
                image_data=data,
                content_type=record.content_type,
                provider_metadata={},
            )
            new_record = service.register_image(
                result,
                "edited",
                prompt=record.prompt,
                source_image_ids=[source_image_id],
            )
            return new_record

        new_record = await asyncio.to_thread(_save)

        return ToolResult(
            content=[
                TextContent(
                    type="text",
                    text=json.dumps(
                        {
                            "image_id": new_record.id,
                            "source_image_id": source_image_id,
                            "original_uri": f"image://{new_record.id}/view",
                        }
                    ),
                )
            ]
        )

    # create_download_link is only available on HTTP transports —
    # stdio has no HTTP server to host the artifact endpoint.
    if transport != "stdio":
        _register_download_link_tool(mcp)

    # -- Style library tools ---------------------------------------------------

    _VALID_STYLE_NAME_RE = re.compile(r"\A[a-zA-Z0-9][a-zA-Z0-9_-]*\Z")

    @mcp.tool(
        name="save_style",
        description=(
            "Save a reusable style preset as a markdown file. "
            "Styles are creative briefs that the LLM interprets "
            "per-provider — not prompt fragments. Use to capture "
            "a visual direction for reuse across conversations."
        ),
        tags={"write"},
        annotations={
            "readOnlyHint": False,
            "destructiveHint": False,
            "openWorldHint": False,
        },
        icons=[Icon(src=_LUCIDE.format("save"), mimeType="image/svg+xml")],
    )
    async def save_style(
        name: str,
        body: str,
        tags: list[str] | None = None,
        provider: str | None = None,
        aspect_ratio: str | None = None,
        quality: str | None = None,
        service: ImageService = Depends(get_service),
        config: ProjectConfig = Depends(get_config),
    ) -> str:
        """Save a style preset to the styles directory.

        Args:
            name: Style identifier — used as the filename (``{name}.md``).
                Alphanumeric, hyphens, and underscores only.
            body: Markdown prose describing the visual direction (the creative
                brief). This is what the LLM reads when applying the style.
            tags: Optional categorization tags for browsing/filtering.
            provider: Suggested provider (``"auto"``, ``"openai"``,
                ``"sd_webui"``). Leave empty for auto-selection.
            aspect_ratio: Default aspect ratio (e.g. ``"16:9"``).
            quality: Default quality level (``"standard"`` or ``"hd"``).

        Returns:
            JSON confirmation with style name, file path, and whether
            it was newly created or overwrote an existing style.
        """
        if not _VALID_STYLE_NAME_RE.match(name):
            msg = (
                f"Invalid style name: {name!r}. "
                "Use only alphanumeric characters, hyphens, and underscores. "
                "Must start with an alphanumeric character."
            )
            raise ValueError(msg)

        existed = service.get_style(name) is not None

        entry = await asyncio.to_thread(
            service.save_style,
            name,
            body,
            config.styles_dir,
            tags=tags,
            provider=provider,
            aspect_ratio=aspect_ratio,
            quality=quality,
        )

        result = {
            "name": entry.name,
            "created": not existed,
        }
        return json.dumps(result, indent=2)

    @mcp.tool(
        name="delete_style",
        description=(
            "Delete a style preset from disk. "
            "Permanently removes the style file and its in-memory entry."
        ),
        tags={"write"},
        annotations={
            "readOnlyHint": False,
            "destructiveHint": True,
            "openWorldHint": False,
        },
        icons=[Icon(src=_LUCIDE.format("trash-2"), mimeType="image/svg+xml")],
    )
    async def delete_style(
        name: str,
        service: ImageService = Depends(get_service),
    ) -> str:
        """Delete a style preset by name.

        Args:
            name: Style identifier to delete.

        Returns:
            JSON confirmation with the deleted style name.
        """
        try:
            await asyncio.to_thread(service.delete_style, name)
        except KeyError:
            msg = (
                f"Style not found: '{name}'. Use style://list to see available styles."
            )
            raise ValueError(msg) from None

        result = {"name": name, "deleted": True}
        return json.dumps(result, indent=2)


def _register_download_link_tool(mcp: FastMCP) -> None:
    """Register the ``create_download_link`` tool on *mcp*.

    Separated from :func:`register_tools` so it can be conditionally
    called only when an HTTP transport is active.

    Args:
        mcp: The :class:`~fastmcp.FastMCP` instance to register the tool on.
    """

    @mcp.tool(
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": False,
        },
        icons=[Icon(src=_LUCIDE.format("link"), mimeType="image/svg+xml")],
    )
    async def create_download_link(
        uri: str,
        ttl_seconds: int = 300,
        service: ImageService = Depends(get_service),
        config: ProjectConfig = Depends(get_config),
    ) -> str:
        """Create a one-time download URL for an image.

        Creates a temporary HTTP endpoint that expires after a single
        download OR when ``ttl_seconds`` elapses, whichever comes first.
        Use this to pass images to other MCP servers (e.g., save to a
        vault, attach to email).

        The URI should be an ``image://`` resource URI, optionally with
        transform parameters (``format``, ``width``, ``height``,
        ``quality``).

        Requires ``IMAGE_GENERATION_MCP_BASE_URL`` to be configured.
        Only available on HTTP transport (not stdio).

        Args:
            uri: A full ``image://`` resource URI, e.g.
                ``image://abc123/view`` or
                ``image://abc123/view?format=webp&width=512``.
            ttl_seconds: Link lifetime in seconds (default 300 / 5 minutes).

        Returns:
            JSON with ``download_url``, ``expires_in_seconds``, and ``uri``.

        Raises:
            ValueError: If ``IMAGE_GENERATION_MCP_BASE_URL`` is not
                configured or the URI references an unknown image.
        """
        from urllib.parse import urlparse

        base_url = (config.server.base_url or "").rstrip("/")
        if not base_url:
            msg = (
                "IMAGE_GENERATION_MCP_BASE_URL is required for download links. "
                "Set it to the public base URL of this server "
                "(e.g. https://mcp.example.com)."
            )
            raise ValueError(msg)

        parsed = urlparse(uri)
        image_id = parsed.netloc or ""
        if not image_id:
            msg = f"Invalid image URI: {uri!r}. Expected format: image://{{image_id}}/view"
            raise ValueError(msg)

        await asyncio.to_thread(service.get_image, image_id)

        from .artifacts import get_artifact_store

        store = get_artifact_store()
        token = store.create_token(uri, ttl_seconds=ttl_seconds)

        download_url = f"{base_url}/artifacts/{token}"
        result = {
            "download_url": download_url,
            "expires_in_seconds": ttl_seconds,
            "uri": uri,
        }
        logger.info(
            "Created download link for image_id=%r ttl=%ds url=%s",
            image_id,
            ttl_seconds,
            download_url,
        )
        return json.dumps(result, indent=2)
