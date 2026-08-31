"""Tests for fail-closed Hermes-to-MicroMeet publication policy."""

from __future__ import annotations

import unittest

from bootstrap import load_module

outbound = load_module("outbound")


class OutboundPolicyTests(unittest.TestCase):
    def test_reply_is_buffered_until_finalized(self) -> None:
        action = outbound.classify_outbound(
            content="partial",
            reply_to="a" * 64,
            metadata=None,
            accepted_follow_reply=True,
        )
        self.assertIs(action, outbound.OutboundAction.BUFFER)

    def test_unsolicited_direct_send_is_suppressed(self) -> None:
        action = outbound.classify_outbound(
            content="setup",
            reply_to=None,
            metadata=None,
            accepted_follow_reply=False,
        )
        self.assertIs(action, outbound.OutboundAction.SUPPRESS)

    def test_completed_accepted_follow_response_is_published(self) -> None:
        action = outbound.classify_outbound(
            content="I received the coordination request.",
            reply_to="a" * 64,
            metadata={"notify": True},
            accepted_follow_reply=True,
        )
        self.assertIs(action, outbound.OutboundAction.PUBLISH)

    def test_generic_final_response_is_suppressed(self) -> None:
        action = outbound.classify_outbound(
            content="This came from another Hermes session.",
            reply_to="a" * 64,
            metadata={"notify": True},
            accepted_follow_reply=False,
        )
        self.assertIs(action, outbound.OutboundAction.SUPPRESS)

    def test_notify_marker_must_be_boolean(self) -> None:
        action = outbound.classify_outbound(
            content="I received the coordination request.",
            reply_to="a" * 64,
            metadata={"notify": "true"},
            accepted_follow_reply=True,
        )
        self.assertIs(action, outbound.OutboundAction.BUFFER)

    def test_operational_failure_is_suppressed_despite_final_marker(self) -> None:
        messages = (
            "⚠️ Provider authentication failed: invalid token",
            "Sorry, I encountered an error (TimeoutError).\nTry again.",
            "The request failed: provider unavailable\nTry again.",
            "HTTP 429 rate limited",
        )
        for message in messages:
            with self.subTest(message=message):
                action = outbound.classify_outbound(
                    content=message,
                    reply_to="a" * 64,
                    metadata={"notify": True},
                    accepted_follow_reply=True,
                )
                self.assertIs(action, outbound.OutboundAction.SUPPRESS)

    def test_publication_requires_boolean_explicit_marker(self) -> None:
        denied = outbound.classify_outbound(
            content="Operator-approved delivery.",
            reply_to=None,
            metadata={"micromeet_publish": "true"},
            accepted_follow_reply=False,
        )
        allowed = outbound.classify_outbound(
            content="Operator-approved delivery.",
            reply_to=None,
            metadata={"micromeet_publish": True},
            accepted_follow_reply=False,
        )
        self.assertIs(denied, outbound.OutboundAction.SUPPRESS)
        self.assertIs(allowed, outbound.OutboundAction.PUBLISH)


if __name__ == "__main__":
    unittest.main()
