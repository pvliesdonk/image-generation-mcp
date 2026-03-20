"""Tests for the in-memory LRU transform cache in ImageService."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from image_generation_mcp.providers.placeholder import PlaceholderImageProvider
from image_generation_mcp.service import ImageService


@pytest.fixture
async def image_id(tmp_path: Path) -> tuple[ImageService, str]:
    """Return (service, image_id) with a registered test image."""
    provider = PlaceholderImageProvider()
    result = await provider.generate("cache test", aspect_ratio="1:1")

    svc = ImageService(scratch_dir=tmp_path, transform_cache_size=4)
    record = svc.register_image(result, "placeholder", prompt="cache test")
    return svc, record.id


# ---------------------------------------------------------------------------
# No-transform bypass
# ---------------------------------------------------------------------------


def test_no_transform_bypass_skips_cache(image_id: tuple[ImageService, str]) -> None:
    """Requests with no transform params read the original and do not cache."""
    service, img_id = image_id

    data, content_type = service.get_transformed_image(img_id)

    # Cache must remain empty — no-transform path is bypassed
    assert len(service._transform_cache) == 0
    assert data  # non-empty bytes
    assert content_type == "image/png"


def test_no_transform_returns_original_bytes(
    image_id: tuple[ImageService, str],
) -> None:
    """No-transform path returns the same bytes as direct file read."""
    service, img_id = image_id
    record = service.get_image(img_id)
    expected = record.original_path.read_bytes()

    data, _ = service.get_transformed_image(img_id)
    assert data == expected


# ---------------------------------------------------------------------------
# Cache population
# ---------------------------------------------------------------------------


def test_transform_populates_cache(image_id: tuple[ImageService, str]) -> None:
    """A transform request stores the result in the cache."""
    service, img_id = image_id

    service.get_transformed_image(img_id, format="webp")

    assert len(service._transform_cache) == 1
    key = (img_id, "webp", 0, 0, 90)
    assert key in service._transform_cache


def test_repeated_transform_returns_identical_bytes(
    image_id: tuple[ImageService, str],
) -> None:
    """Repeated requests for the same transform return the exact same bytes."""
    service, img_id = image_id

    first, _ = service.get_transformed_image(img_id, format="webp", quality=80)
    second, _ = service.get_transformed_image(img_id, format="webp", quality=80)

    assert first == second
    # Only one entry in cache (same key)
    assert len(service._transform_cache) == 1


def test_different_params_produce_separate_cache_entries(
    image_id: tuple[ImageService, str],
) -> None:
    """Different transform params each get their own cache entry."""
    service, img_id = image_id

    service.get_transformed_image(img_id, format="webp")
    service.get_transformed_image(img_id, format="jpeg")
    service.get_transformed_image(img_id, width=100)

    assert len(service._transform_cache) == 3


# ---------------------------------------------------------------------------
# LRU eviction
# ---------------------------------------------------------------------------


def test_cache_evicts_oldest_when_full(image_id: tuple[ImageService, str]) -> None:
    """When cache is at max size, the least-recently-used entry is evicted."""
    service, img_id = image_id
    # service has transform_cache_size=4

    # Fill the cache to max
    keys = []
    for q in (70, 75, 80, 85):
        service.get_transformed_image(img_id, format="jpeg", quality=q)
        keys.append((img_id, "jpeg", 0, 0, q))

    assert len(service._transform_cache) == 4

    # Adding a 5th entry must evict the first (oldest) key
    service.get_transformed_image(img_id, format="jpeg", quality=90)
    assert len(service._transform_cache) == 4
    assert keys[0] not in service._transform_cache
    assert (img_id, "jpeg", 0, 0, 90) in service._transform_cache


def test_cache_hit_moves_to_end_preventing_eviction(
    image_id: tuple[ImageService, str],
) -> None:
    """Accessing a cached entry promotes it so it survives later evictions."""
    service, img_id = image_id
    # service has transform_cache_size=4

    # Add 4 entries
    for q in (70, 75, 80, 85):
        service.get_transformed_image(img_id, format="jpeg", quality=q)

    # Re-access the oldest entry to promote it
    oldest_key = (img_id, "jpeg", 0, 0, 70)
    service.get_transformed_image(img_id, format="jpeg", quality=70)

    # Now add a new entry — the second-oldest (q=75) should be evicted, not q=70
    service.get_transformed_image(img_id, format="jpeg", quality=90)

    assert oldest_key in service._transform_cache
    evicted_key = (img_id, "jpeg", 0, 0, 75)
    assert evicted_key not in service._transform_cache


# ---------------------------------------------------------------------------
# Cache cleared on aclose
# ---------------------------------------------------------------------------


async def test_cache_cleared_on_aclose(image_id: tuple[ImageService, str]) -> None:
    """aclose() empties the transform cache."""
    service, img_id = image_id

    service.get_transformed_image(img_id, format="webp")
    assert len(service._transform_cache) == 1

    await service.aclose()

    assert len(service._transform_cache) == 0
