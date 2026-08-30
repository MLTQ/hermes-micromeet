"""Tests for immutable-post handling in the Hermes gateway adapter."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock

from bootstrap import load_plugin


class AdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_stream_preview_publishes_only_when_finalized(self) -> None:
        adapter_module = load_plugin().adapter
        adapter = object.__new__(adapter_module.MicroMeetAdapter)
        adapter._drafts = {}
        adapter._draft_sequence = 0
        adapter._publish = AsyncMock(
            return_value=adapter_module.SendResult(success=True, message_id="signed-post")
        )

        preview = await adapter.send(
            "a" * 64,
            "partial",
            reply_to="b" * 64,
            metadata={"expect_edits": True},
        )
        self.assertTrue(preview.success)
        adapter._publish.assert_not_awaited()

        update = await adapter.edit_message(
            "a" * 64, preview.message_id, "complete", finalize=False
        )
        self.assertTrue(update.success)
        adapter._publish.assert_not_awaited()

        final = await adapter.edit_message(
            "a" * 64, preview.message_id, "complete", finalize=True
        )
        self.assertEqual(final.message_id, "signed-post")
        adapter._publish.assert_awaited_once()
        self.assertNotIn(preview.message_id, adapter._drafts)

    async def test_immediate_identical_delivery_reuses_signed_post(self) -> None:
        adapter_module = load_plugin().adapter
        adapter = object.__new__(adapter_module.MicroMeetAdapter)
        adapter._recent_deliveries = {}
        adapter.service = type(
            "Service",
            (),
            {
                "run": AsyncMock(
                    return_value={"ok": True, "result": {"object_id": "signed-once"}}
                )
            },
        )()
        first = await adapter._publish("a" * 64, "same error", None, None)
        second = await adapter._publish("a" * 64, "same error", "b" * 64, None)
        self.assertEqual(first.message_id, "signed-once")
        self.assertEqual(second.message_id, "signed-once")
        adapter.service.run.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
