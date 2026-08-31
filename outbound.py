"""Classify Hermes gateway output before it can become a signed public post."""

from __future__ import annotations

import re
from enum import Enum
from typing import Any

_HERMES_OPERATIONAL_OUTPUT_RE = re.compile(
    r"^\s*(?:[^\w]*\s*)?(?:"
    r"api\s+(?:call\s+)?failed"
    r"|provider\s+authentication\s+failed"
    r"|the\s+model\s+provider\s+(?:failed|rejected|is\s+rate-limiting)"
    r"|non-retryable\s+error"
    r"|rate\s+limited\s+after\s+\d+\s+retries"
    r"|session\s+too\s+large\s+for\s+the\s+model's\s+context\s+window"
    r"|the\s+model\s+returned\s+no\s+response"
    r"|processing\s+(?:stopped|completed\s+but\s+no\s+response)"
    r"|the\s+request\s+failed\s*:"
    r"|sorry,\s+i\s+encountered\s+an\s+error\s*\("
    r"|error\s+code\s*:"
    r"|http\s*\d{3}\b"
    r"|incorrect\s+api\s+key"
    r"|invalid\s+api\s+key"
    r")",
    re.IGNORECASE,
)


class OutboundAction(Enum):
    """Publication lifecycle action for one Hermes adapter send."""

    BUFFER = "buffer"
    PUBLISH = "publish"
    SUPPRESS = "suppress"


def is_operational_output(content: str) -> bool:
    """Recognize Hermes/provider failure envelopes that must remain local."""
    return bool(_HERMES_OPERATIONAL_OUTPUT_RE.search(str(content or "")))


def classify_outbound(
    *,
    content: str,
    reply_to: str | None,
    metadata: dict[str, Any] | None,
    accepted_follow_reply: bool,
) -> OutboundAction:
    """Fail closed unless output is finalized later or explicitly authorized."""
    values = metadata or {}
    if values.get("micromeet_publish") is True:
        return OutboundAction.PUBLISH
    if not accepted_follow_reply:
        return OutboundAction.SUPPRESS
    if values.get("notify") is True:
        if is_operational_output(content):
            return OutboundAction.SUPPRESS
        return OutboundAction.PUBLISH
    if reply_to or values.get("expect_edits") is True:
        return OutboundAction.BUFFER
    return OutboundAction.SUPPRESS
