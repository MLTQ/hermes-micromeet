"""Tests for immutable-post handling in the Hermes gateway adapter."""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, patch

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
        adapter._delivery_lock = asyncio.Lock()

        async def publish_once(*_args, **_kwargs):
            await asyncio.sleep(0.01)
            return {"ok": True, "result": {"object_id": "signed-once"}}

        adapter.service = type(
            "Service",
            (),
            {"run": AsyncMock(side_effect=publish_once)},
        )()
        first, second = await asyncio.gather(
            adapter._publish("a" * 64, "same error", None, None),
            adapter._publish("a" * 64, "same error", "b" * 64, None),
        )
        self.assertEqual(first.message_id, "signed-once")
        self.assertEqual(second.message_id, "signed-once")
        adapter.service.run.assert_awaited_once()

    def test_replyless_idempotency_key_expires_after_five_seconds(self) -> None:
        adapter_module = load_plugin().adapter
        with patch.object(adapter_module.time, "time", return_value=100.0):
            first = adapter_module.MicroMeetAdapter._delivery_key(
                "a" * 64, "same system notice", None, None
            )
        with patch.object(adapter_module.time, "time", return_value=106.0):
            later = adapter_module.MicroMeetAdapter._delivery_key(
                "a" * 64, "same system notice", None, None
            )
        self.assertNotEqual(first, later)


if __name__ == "__main__":
    unittest.main()
