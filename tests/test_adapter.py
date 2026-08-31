"""Tests for immutable-post handling in the Hermes gateway adapter."""

from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from bootstrap import load_plugin


class AdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_setup_notice_is_suppressed_without_publication(self) -> None:
        adapter_module = load_plugin().adapter
        adapter = object.__new__(adapter_module.MicroMeetAdapter)
        adapter._drafts = {}
        adapter._draft_sequence = 0
        adapter._publish = AsyncMock()

        result = await adapter.send(
            "a" * 64,
            "📬 No home channel is set for Micromeet.",
        )

        self.assertTrue(result.success)
        self.assertTrue(result.raw_response["suppressed"])
        self.assertIsNone(result.message_id)
        adapter._publish.assert_not_awaited()

    async def test_provider_error_reply_remains_an_unpublished_draft(self) -> None:
        adapter_module = load_plugin().adapter
        adapter = object.__new__(adapter_module.MicroMeetAdapter)
        adapter._drafts = {}
        adapter._draft_sequence = 0
        adapter._publish = AsyncMock()

        result = await adapter.send(
            "a" * 64,
            "⚠️ Provider authentication failed.",
            reply_to="b" * 64,
        )

        self.assertTrue(result.success)
        self.assertTrue(result.message_id.startswith("micromeet-draft:"))
        self.assertIn(result.message_id, adapter._drafts)
        adapter._publish.assert_not_awaited()

    async def test_unfinalized_drafts_are_bounded(self) -> None:
        adapter_module = load_plugin().adapter
        adapter = object.__new__(adapter_module.MicroMeetAdapter)
        adapter._drafts = {
            f"micromeet-draft:{index}": ("thread", "body", None, None) for index in range(1, 65)
        }
        adapter._draft_sequence = 64
        adapter._publish = AsyncMock()

        result = await adapter.send("a" * 64, "pending", reply_to="b" * 64)

        self.assertEqual(len(adapter._drafts), 64)
        self.assertNotIn("micromeet-draft:1", adapter._drafts)
        self.assertIn(result.message_id, adapter._drafts)
        adapter._publish.assert_not_awaited()

    async def test_explicit_direct_delivery_is_published(self) -> None:
        adapter_module = load_plugin().adapter
        adapter = object.__new__(adapter_module.MicroMeetAdapter)
        adapter._drafts = {}
        adapter._draft_sequence = 0
        adapter._publish = AsyncMock(
            return_value=adapter_module.SendResult(success=True, message_id="signed-post")
        )

        result = await adapter.send(
            "a" * 64,
            "Operator-approved delivery.",
            metadata={"micromeet_publish": True},
        )

        self.assertEqual(result.message_id, "signed-post")
        adapter._publish.assert_awaited_once()

    async def test_notifications_can_be_disabled_without_starting_watcher(self) -> None:
        adapter_module = load_plugin().adapter
        adapter = object.__new__(adapter_module.MicroMeetAdapter)
        adapter._running = False
        adapter.settings = SimpleNamespace(notifications=False)
        adapter.service = SimpleNamespace(
            ensure_status=AsyncMock(
                return_value={
                    "ok": True,
                    "result": {"identity": {"author_id": "ed25519:" + "a" * 64}},
                }
            ),
            start_watcher=AsyncMock(),
            stop_owned_daemon=AsyncMock(),
        )
        adapter.cursor = SimpleNamespace(starting=AsyncMock(return_value=0))
        adapter._mark_connected = Mock()

        self.assertTrue(await adapter.connect())
        adapter.cursor.starting.assert_not_awaited()
        adapter.service.start_watcher.assert_not_awaited()
        adapter._mark_connected.assert_called_once_with()

    async def test_remote_notice_wakes_hermes_then_commits_cursor(self) -> None:
        adapter_module = load_plugin().adapter
        adapter = object.__new__(adapter_module.MicroMeetAdapter)
        adapter._own_author_id = "ed25519:" + "a" * 64
        adapter.client = object()
        order = []
        adapter.cursor = SimpleNamespace(commit=lambda cursor: order.append(("commit", cursor)))

        async def handle_message(event):
            order.append(("handle", event))

        event = object()
        adapter.handle_message = handle_message
        adapter._event = Mock(return_value=event)
        notice = {
            "cursor": 7,
            "kind": "post",
            "object_id": "b" * 64,
            "author": {"id": "ed25519:" + "c" * 64},
        }
        projected = object()
        with patch.object(adapter_module, "project_notice", return_value=projected):
            await adapter._accept_notice(notice)

        self.assertEqual(order, [("handle", event), ("commit", 7)])
        adapter._event.assert_called_once_with(projected)

    def test_follow_notification_metadata_is_explicit_and_untrusted(self) -> None:
        adapter_module = load_plugin().adapter
        adapter = object.__new__(adapter_module.MicroMeetAdapter)
        adapter.platform = adapter_module.Platform.LOCAL
        projected = adapter_module.ProjectedMessage(
            object_id="a" * 64,
            thread_id="b" * 64,
            topic_id="c" * 64,
            title="Coordination",
            body="Try the patch.",
            author_id="ed25519:" + "d" * 64,
            author_name="peer",
            created_at="2026-08-30T01:00:00Z",
            received_at="2026-08-30T01:00:02Z",
            reply_to=None,
            content_trust="untrusted_remote",
            raw={},
        )

        event = adapter._event(projected)

        metadata = event.raw_message["micromeet_notification"]
        self.assertTrue(metadata["follow_notification"])
        self.assertEqual(metadata["content_trust"], "untrusted_remote")
        self.assertEqual(metadata["received_at"], projected.received_at)
        self.assertIn("untrusted external data", event.text)
        self.assertIn(projected.body, event.text)

    def test_notification_framing_neutralizes_peer_slash_commands(self) -> None:
        adapter_module = load_plugin().adapter
        projected = adapter_module.ProjectedMessage(
            object_id="a" * 64,
            thread_id="b" * 64,
            topic_id="c" * 64,
            title="Coordination",
            body="/restart",
            author_id="ed25519:" + "d" * 64,
            author_name="peer",
            created_at="2026-08-30T01:00:00Z",
            received_at="2026-08-30T01:00:02Z",
            reply_to=None,
            content_trust="untrusted_remote",
            raw={},
        )

        framed = adapter_module._notification_text(projected)

        self.assertFalse(framed.startswith("/"))
        self.assertTrue(framed.endswith("/restart"))

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
        )
        self.assertTrue(preview.success)
        adapter._publish.assert_not_awaited()

        update = await adapter.edit_message(
            "a" * 64, preview.message_id, "complete", finalize=False
        )
        self.assertTrue(update.success)
        adapter._publish.assert_not_awaited()

        final = await adapter.edit_message("a" * 64, preview.message_id, "complete", finalize=True)
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
