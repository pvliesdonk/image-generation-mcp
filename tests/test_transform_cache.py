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
    key = (img_id, "webp", 0, 0, 90, 0, 0, 0, 0, 0, "")
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
        keys.append((img_id, "jpeg", 0, 0, q, 0, 0, 0, 0, 0, ""))

    assert len(service._transform_cache) == 4

    # Adding a 5th entry must evict the first (oldest) key
    service.get_transformed_image(img_id, format="jpeg", quality=90)
    assert len(service._transform_cache) == 4
    assert keys[0] not in service._transform_cache
    assert (img_id, "jpeg", 0, 0, 90, 0, 0, 0, 0, 0, "") in service._transform_cache


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
    oldest_key = (img_id, "jpeg", 0, 0, 70, 0, 0, 0, 0, 0, "")
    service.get_transformed_image(img_id, format="jpeg", quality=70)

    # Now add a new entry — the second-oldest (q=75) should be evicted, not q=70
    service.get_transformed_image(img_id, format="jpeg", quality=90)

    assert oldest_key in service._transform_cache
    evicted_key = (img_id, "jpeg", 0, 0, 75, 0, 0, 0, 0, 0, "")
    assert evicted_key not in service._transform_cache


# ---------------------------------------------------------------------------
# Cache cleared on aclose
# ---------------------------------------------------------------------------


async def test_cache_disabled_when_size_zero(tmp_path: Path) -> None:
    """Setting transform_cache_size=0 disables caching entirely."""
    provider = PlaceholderImageProvider()
    result = await provider.generate("zero cache test", aspect_ratio="1:1")

    svc = ImageService(scratch_dir=tmp_path, transform_cache_size=0)
    record = svc.register_image(result, "placeholder", prompt="zero cache test")

    # A transform request should return data but not grow the cache
    data, ct = svc.get_transformed_image(record.id, format="webp")
    assert data  # non-empty bytes
    assert ct == "image/webp"
    assert len(svc._transform_cache) == 0

    # Second call also returns data, cache still empty
    data2, _ = svc.get_transformed_image(record.id, format="webp")
    assert data2 == data
    assert len(svc._transform_cache) == 0


async def test_cache_cleared_on_aclose(image_id: tuple[ImageService, str]) -> None:
    """aclose() empties the transform cache."""
    service, img_id = image_id

    service.get_transformed_image(img_id, format="webp")
    assert len(service._transform_cache) == 1

    await service.aclose()

    assert len(service._transform_cache) == 0


# ---------------------------------------------------------------------------
# Transform paths: format conversion and proportional resize
# ---------------------------------------------------------------------------


class TestTransformCacheTransforms:
    """Tests for actual transform paths to boost coverage."""

    def test_format_conversion_cached(self, image_id: tuple) -> None:
        """Format conversion result is cached."""
        service, img_id = image_id
        # First call - cache miss
        data1, ct1 = service.get_transformed_image(img_id, format="webp")
        assert ct1 == "image/webp"
        # Second call - cache hit
        data2, _ct2 = service.get_transformed_image(img_id, format="webp")
        assert data1 == data2

    def test_proportional_resize_by_width(self, image_id: tuple) -> None:
        """Width-only resize uses proportional scaling."""
        service, img_id = image_id
        data, _ct = service.get_transformed_image(img_id, width=128)
        # Should return valid image data
        assert len(data) > 0

    def test_proportional_resize_by_height(self, image_id: tuple) -> None:
        """Height-only resize uses proportional scaling."""
        service, img_id = image_id
        data, _ct = service.get_transformed_image(img_id, height=128)
        assert len(data) > 0

    def test_crop_to_exact_dimensions(self, image_id: tuple) -> None:
        """Both width and height specified crops to exact dimensions."""
        service, img_id = image_id
        data, _ct = service.get_transformed_image(img_id, width=64, height=64)
        assert len(data) > 0


# ---------------------------------------------------------------------------
# New transform params: crop_region, rotate, flip
# ---------------------------------------------------------------------------


def test_crop_region_cached(image_id: tuple[ImageService, str]) -> None:
    """crop_region transform is cached with its own key."""
    service, img_id = image_id
    record = service.get_image(img_id)
    w, h = record.original_dimensions
    data, _ = service.get_transformed_image(
        img_id, crop_x=0, crop_y=0, crop_w=w // 2, crop_h=h // 2
    )
    assert len(data) > 0
    key = (img_id, "", 0, 0, 90, 0, 0, w // 2, h // 2, 0, "")
    assert key in service._transform_cache


def test_rotate_cached(image_id: tuple[ImageService, str]) -> None:
    """rotate transform is cached separately from no-rotate."""
    service, img_id = image_id
    service.get_transformed_image(img_id, rotate=90)
    service.get_transformed_image(img_id, rotate=180)
    assert len(service._transform_cache) == 2


def test_flip_cached(image_id: tuple[ImageService, str]) -> None:
    """flip transform produces its own cache entry."""
    service, img_id = image_id
    service.get_transformed_image(img_id, flip="horizontal")
    service.get_transformed_image(img_id, flip="vertical")
    assert len(service._transform_cache) == 2


def test_different_new_params_separate_entries(
    image_id: tuple[ImageService, str],
) -> None:
    """Different new transform param combinations are cached separately."""
    service, img_id = image_id
    service.get_transformed_image(img_id, rotate=90)
    service.get_transformed_image(img_id, rotate=90, flip="horizontal")
    service.get_transformed_image(img_id, format="webp", rotate=90)
    assert len(service._transform_cache) == 3
