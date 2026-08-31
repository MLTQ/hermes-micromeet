"""Tests for fail-closed Hermes-to-MicroMeet publication policy."""

from __future__ import annotations

import unittest

from bootstrap import load_module

outbound = load_module("outbound")


class OutboundPolicyTests(unittest.TestCase):
    def test_reply_is_buffered_until_finalized(self) -> None:
        action = outbound.classify_outbound(reply_to="a" * 64, metadata=None)
        self.assertIs(action, outbound.OutboundAction.BUFFER)

    def test_unsolicited_direct_send_is_suppressed(self) -> None:
        action = outbound.classify_outbound(reply_to=None, metadata=None)
        self.assertIs(action, outbound.OutboundAction.SUPPRESS)

    def test_publication_requires_boolean_explicit_marker(self) -> None:
        denied = outbound.classify_outbound(
            reply_to=None,
            metadata={"micromeet_publish": "true"},
        )
        allowed = outbound.classify_outbound(
            reply_to=None,
            metadata={"micromeet_publish": True},
        )
        self.assertIs(denied, outbound.OutboundAction.SUPPRESS)
        self.assertIs(allowed, outbound.OutboundAction.PUBLISH)


if __name__ == "__main__":
    unittest.main()
