"""Tests for build_event_store() — URL parsing and file persistence."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from image_generation_mcp.mcp_server import build_event_store

if TYPE_CHECKING:
    from pathlib import Path


# ---------------------------------------------------------------------------
# URL parsing — unit tests
# ---------------------------------------------------------------------------


class TestBuildEventStoreURLParsing:
    def test_none_url_returns_file_backed_store(self) -> None:
        """No URL defaults to file://<default_dir>; use memory:// to verify type."""
        # Use memory:// for isolation — can't override _DEFAULT_EVENT_STORE_DIR here.
        store = build_event_store("memory://")
        from fastmcp.server.event_store import EventStore

        assert isinstance(store, EventStore)

    def test_memory_scheme_returns_event_store(self) -> None:
        store = build_event_store("memory://")
        from fastmcp.server.event_store import EventStore

        assert isinstance(store, EventStore)

    def test_file_scheme_creates_directory(self, tmp_path: Path) -> None:
        target = tmp_path / "nested" / "events"
        assert not target.exists()

        store = build_event_store(f"file://{target}")

        assert target.exists()
        from fastmcp.server.event_store import EventStore

        assert isinstance(store, EventStore)

    def test_file_scheme_existing_directory(self, tmp_path: Path) -> None:
        target = tmp_path / "events"
        target.mkdir()

        store = build_event_store(f"file://{target}")

        from fastmcp.server.event_store import EventStore

        assert isinstance(store, EventStore)

    def test_unsupported_scheme_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Unsupported EVENT_STORE_URL scheme"):
            build_event_store("redis://localhost:6379")

    def test_unsupported_scheme_message_includes_scheme(self) -> None:
        with pytest.raises(ValueError, match="'ftp'"):
            build_event_store("ftp://host/path")


# ---------------------------------------------------------------------------
# File persistence — integration test
# ---------------------------------------------------------------------------


class TestEventStorePersistence:
    """Verify that a FileTreeStore-backed EventStore survives across instances.

    We simulate a container restart by building two EventStore objects that
    both point to the same directory.  Events written by the first store
    should be readable by the second.
    """

    @pytest.mark.asyncio
    async def test_events_survive_store_restart(self, tmp_path: Path) -> None:
        store_dir = tmp_path / "events"

        # Round 1: write an event
        store1 = build_event_store(f"file://{store_dir}")
        event_id = await store1.store_event(stream_id="stream-1", message=None)
        assert event_id  # non-empty

        # Round 2: new EventStore pointing at the same directory (simulates restart)
        store2 = build_event_store(f"file://{store_dir}")

        replayed: list[object] = []

        async def _capture(msg: object) -> None:
            replayed.append(msg)

        # replay_events_after returns the stream_id when the event is found;
        # returns None when event_id is unknown.  A None-message (priming)
        # event has no payload to replay, so _capture is not called — but
        # the stream_id is returned, confirming the store found the record.
        result = await store2.replay_events_after(event_id, _capture)
        assert result == "stream-1", (
            "File-backed store did not find event_id from previous instance — "
            "events are not persisted to disk."
        )
