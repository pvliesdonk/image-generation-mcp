"""Image generation provider protocol and types.

Defines the ImageProvider protocol for image generation backends,
the ImageResult value type, and the exception hierarchy.

Ported from questfoundry — PromptDistiller and ImageBrief are not
included; MCP clients write prompts directly.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from image_generation_mcp.providers.capabilities import ProviderCapabilities


@dataclass(frozen=True)
class ImageResult:
    """Result of an image generation call.

    Attributes:
        image_data: Raw image bytes.
        content_type: MIME type (e.g., ``image/png``).
        provider_metadata: Provider-specific metadata (model, seed, etc.).
    """

    image_data: bytes
    content_type: str = "image/png"
    provider_metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def size_bytes(self) -> int:
        """Size of image data in bytes."""
        return len(self.image_data)

    @classmethod
    def from_base64(
        cls,
        b64_data: str,
        content_type: str = "image/png",
        **metadata: Any,
    ) -> ImageResult:
        """Create from base64-encoded image data.

        Args:
            b64_data: Base64-encoded image string.
            content_type: MIME type of the image.
            **metadata: Additional provider metadata.

        Returns:
            ImageResult with decoded bytes.
        """
        return cls(
            image_data=base64.b64decode(b64_data),
            content_type=content_type,
            provider_metadata=metadata,
        )


@runtime_checkable
class ImageProvider(Protocol):
    """Protocol for image generation backends.

    All image providers must implement the ``generate`` method.
    The protocol is runtime-checkable for isinstance() validation.
    """

    async def generate(
        self,
        prompt: str,
        *,
        negative_prompt: str | None = None,
        aspect_ratio: str = "1:1",
        quality: str = "standard",
        background: str = "opaque",
        model: str | None = None,
    ) -> ImageResult:
        """Generate an image from a text prompt.

        Args:
            prompt: Positive text prompt describing the desired image.
            negative_prompt: Things to avoid (provider support varies).
            aspect_ratio: Desired aspect ratio (e.g., ``16:9``, ``1:1``).
            quality: Quality level (``standard``, ``hd``).
            background: Background transparency (``opaque``, ``transparent``).
                Only supported by some providers.
            model: Specific model to use (e.g., a checkpoint name for SD WebUI,
                or ``"dall-e-3"`` for OpenAI). Overrides the provider's
                configured default for this call.

        Returns:
            ImageResult with generated image data.

        Raises:
            ImageProviderError: If generation fails.
        """
        ...

    async def discover_capabilities(self) -> ProviderCapabilities:
        """Discover this provider's capabilities at startup.

        Called once during server lifespan after provider construction.
        Results are cached for the server lifetime.

        Returns:
            ProviderCapabilities describing models and features.

        Raises:
            Exception: Any error during discovery (caller handles gracefully).
        """
        ...


SUPPORTED_ASPECT_RATIOS: tuple[str, ...] = ("1:1", "16:9", "9:16", "3:2", "2:3")
"""Aspect ratios supported across providers."""

SUPPORTED_QUALITY_LEVELS: tuple[str, ...] = ("standard", "hd")
"""Quality levels supported across providers."""

SUPPORTED_BACKGROUNDS: tuple[str, ...] = ("opaque", "transparent")
"""Background transparency modes supported across providers."""


class ImageProviderError(Exception):
    """Base exception for image provider errors."""

    def __init__(self, provider: str, message: str) -> None:
        self.provider = provider
        super().__init__(f"[{provider}] {message}")


class ImageContentPolicyError(ImageProviderError):
    """Raised when image generation is rejected by content policy."""


class ImageProviderConnectionError(ImageProviderError):
    """Raised when the image provider is unreachable."""
