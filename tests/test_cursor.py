"""Tests for first-run and durable MicroMeet inbox cursor policy."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from bootstrap import load_module

cursor_module = load_module("cursor")


class FakeState:
    def __init__(self, saved=None) -> None:
        self.saved = saved

    def get(self, _key, default=None):
        return self.saved if self.saved is not None else default

    def set(self, _key, value) -> None:
        self.saved = value


class CursorTests(unittest.IsolatedAsyncioTestCase):
    async def test_existing_cursor_wins_without_scanning(self) -> None:
        service = SimpleNamespace(run=AsyncMock())
        cursor = cursor_module.InboxCursor(
            state=FakeState(42), service=service, page_size=100, replay_existing=False
        )
        self.assertEqual(await cursor.starting(), 42)
        service.run.assert_not_awaited()

    async def test_first_run_scans_to_current_head(self) -> None:
        service = SimpleNamespace(
            run=AsyncMock(
                side_effect=[
                    {"ok": True, "result": {"items": [{"cursor": 3}], "next_cursor": 3}},
                    {"ok": True, "result": {"items": []}},
                ]
            )
        )
        state = FakeState()
        cursor = cursor_module.InboxCursor(
            state=state, service=service, page_size=100, replay_existing=False
        )
        self.assertEqual(await cursor.starting(), 3)
        self.assertEqual(state.saved, 3)


if __name__ == "__main__":
    unittest.main()
