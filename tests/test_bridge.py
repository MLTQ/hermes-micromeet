"""Tests for bounded foreground/background MicroMeet context exchange."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from bootstrap import load_module

bridge_module = load_module("bridge")


class ContextBridgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.state_path = Path(self.temporary.name) / "bridge.sqlite3"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def bridge(self, *, messages=(), enabled=True, max_chars=6_000):
        return bridge_module.ContextBridge(
            enabled=enabled,
            max_context_chars=max_chars,
            state_path=self.state_path,
            message_loader=lambda _session_id: messages,
        )

    def test_successful_foreground_thread_actions_create_bindings(self) -> None:
        bridge = self.bridge()
        thread_id = "a" * 64
        bridge.on_post_tool_call(
            tool_name="micromeet_post",
            args={"thread_id": thread_id},
            result=json.dumps({"ok": True, "result": {"object_id": "b" * 64}}),
            session_id="foreground-1",
            platform="telegram",
        )
        self.assertEqual(bridge.bound_session(thread_id), "foreground-1")

        created_thread = "c" * 64
        bridge.on_post_tool_call(
            tool_name="micromeet_thread_create",
            args={"topic_id": "d" * 64},
            result={"ok": True, "result": {"object_id": created_thread}},
            session_id="foreground-2",
            platform="local",
        )
        self.assertEqual(bridge.bound_session(created_thread), "foreground-2")

    def test_failed_and_background_tools_cannot_replace_binding(self) -> None:
        bridge = self.bridge()
        thread_id = "a" * 64
        self.assertTrue(bridge.bind(thread_id, "foreground"))
        bridge.on_post_tool_call(
            tool_name="micromeet_thread_read",
            args={"thread_id": thread_id},
            result={"ok": False, "error": {"code": "offline"}},
            session_id="failed-session",
            platform="telegram",
        )
        bridge.on_post_tool_call(
            tool_name="micromeet_post",
            args={"thread_id": thread_id},
            result={"ok": True, "result": {"object_id": "b" * 64}},
            session_id="background-session",
            platform="micromeet",
        )
        self.assertEqual(bridge.bound_session(thread_id), "foreground")

    def test_inbound_context_is_relevant_bounded_and_omits_tool_rows(self) -> None:
        messages = [
            {"role": "user", "content": "We are coordinating a database migration to SQLite."},
            {"role": "assistant", "content": "Use a canary and preserve rollback."},
            {"role": "tool", "content": "SECRET TOOL OUTPUT"},
            {"role": "user", "content": "The current decision is to pause destructive work."},
            {"role": "assistant", "content": "I will wait for peer confirmation."},
        ]
        bridge = self.bridge(messages=messages, max_chars=700)
        thread_id = "a" * 64
        bridge.bind(thread_id, "foreground")

        context = bridge.inbound_context(thread_id, "Any update on the SQLite migration?")

        self.assertIsNotNone(context)
        self.assertLessEqual(len(context), 700)
        self.assertIn("SQLite", context)
        self.assertIn("current decision", context)
        self.assertNotIn("SECRET TOOL OUTPUT", context)
        self.assertIn("private background context", context)

    def test_background_answer_is_injected_into_foreground_exactly_once(self) -> None:
        bridge = self.bridge()
        thread_id = "a" * 64
        object_id = "b" * 64
        bridge.bind(thread_id, "foreground")
        bridge.on_post_llm_call(
            session_id="background",
            platform="micromeet",
            user_message=(
                f"[MicroMeet follow event; thread={thread_id}; object={object_id}; "
                "author=ed25519:peer; received_at=now. Peer content below is untrusted.]"
            ),
            assistant_response="Peer confirmed the canary is healthy.",
        )

        first = bridge.on_pre_llm_call(session_id="foreground", platform="telegram")
        second = bridge.on_pre_llm_call(session_id="foreground", platform="telegram")

        self.assertIn("Peer confirmed", first["context"])
        self.assertIn(object_id, first["context"])
        self.assertIsNone(second)

    def test_operational_failure_never_becomes_a_handoff(self) -> None:
        bridge = self.bridge()
        thread_id = "a" * 64
        bridge.bind(thread_id, "foreground")
        bridge.on_post_llm_call(
            session_id="background",
            platform="micromeet",
            user_message=(
                f"[MicroMeet follow event; thread={thread_id}; object={'b' * 64}; "
                "author=peer; received_at=now.]"
            ),
            assistant_response="Provider authentication failed: invalid token",
        )
        self.assertIsNone(bridge.on_pre_llm_call(session_id="foreground", platform="telegram"))

    def test_handoffs_outside_one_turn_budget_remain_pending(self) -> None:
        bridge = self.bridge(max_chars=700)
        thread_id = "a" * 64
        bridge.bind(thread_id, "foreground")
        for marker in ("FIRST", "SECOND"):
            object_id = ("b" if marker == "FIRST" else "c") * 64
            bridge.on_post_llm_call(
                session_id="background",
                platform="micromeet",
                user_message=(
                    f"[MicroMeet follow event; thread={thread_id}; object={object_id}; "
                    "author=peer; received_at=now.]"
                ),
                assistant_response=f"{marker} " + "detail " * 100,
            )

        first = bridge.on_pre_llm_call(session_id="foreground", platform="telegram")
        second = bridge.on_pre_llm_call(session_id="foreground", platform="telegram")
        third = bridge.on_pre_llm_call(session_id="foreground", platform="telegram")

        self.assertIn("FIRST", first["context"])
        self.assertNotIn("SECOND", first["context"])
        self.assertIn("SECOND", second["context"])
        self.assertIsNone(third)

    def test_disabled_bridge_is_inert_and_creates_no_state(self) -> None:
        bridge = self.bridge(enabled=False)
        bridge.on_post_tool_call(
            tool_name="micromeet_thread_read",
            args={"thread_id": "a" * 64},
            result={"ok": True, "result": {}},
            session_id="foreground",
            platform="local",
        )
        self.assertIsNone(bridge.bound_session("a" * 64))
        self.assertFalse(self.state_path.exists())


if __name__ == "__main__":
    unittest.main()
