"""Classify Hermes gateway output before it can become a signed public post."""

from __future__ import annotations

from enum import Enum
from typing import Any


class OutboundAction(Enum):
    """Publication lifecycle action for one Hermes adapter send."""

    BUFFER = "buffer"
    PUBLISH = "publish"
    SUPPRESS = "suppress"


def classify_outbound(
    *,
    reply_to: str | None,
    metadata: dict[str, Any] | None,
) -> OutboundAction:
    """Fail closed unless output is finalized later or explicitly authorized."""
    values = metadata or {}
    if values.get("micromeet_publish") is True:
        return OutboundAction.PUBLISH
    if reply_to or values.get("expect_edits") is True:
        return OutboundAction.BUFFER
    return OutboundAction.SUPPRESS
