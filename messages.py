"""Project verified MicroMeet notices into gateway-ready messages."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .runner import MmClient


class ProjectionError(ValueError):
    """A notice could not be projected without violating the local contract."""


class HistoryWindowMiss(ProjectionError):
    """A valid notice references a post older than the bounded thread view."""


@dataclass(frozen=True)
class ProjectedMessage:
    object_id: str
    thread_id: str
    topic_id: str
    title: str
    body: str
    author_id: str
    author_name: str
    created_at: str
    received_at: str
    reply_to: str | None
    content_trust: str
    raw: dict[str, Any]


def project_notice(client: MmClient, notice: dict[str, Any]) -> ProjectedMessage | None:
    """Hydrate a thread/post notice from the verified local MicroMeet index."""
    if notice.get("kind") not in {"thread_root", "post"}:
        return None
    object_id = _hex_id(notice.get("object_id"), "object_id")
    thread_id = _hex_id(notice.get("thread_id"), "thread_id")
    page = client.run(["thread", "read", thread_id, "--limit", "100"])
    if not page.get("ok"):
        error = page.get("error") or {}
        raise ProjectionError(
            f"thread hydration failed ({error.get('code', 'unknown')}): "
            f"{error.get('message', 'unknown error')}"
        )
    result = page.get("result")
    if not isinstance(result, dict):
        raise ProjectionError("thread hydration omitted its result object")
    posts = result.get("posts")
    if not isinstance(posts, list):
        raise ProjectionError("thread hydration omitted its posts array")
    post = next(
        (item for item in posts if isinstance(item, dict) and item.get("id") == object_id),
        None,
    )
    if post is None:
        raise HistoryWindowMiss(
            "announced object was older than the bounded hydrated thread history"
        )

    author = post.get("author")
    if not isinstance(author, dict) or author.get("signature_valid") is not True:
        raise ProjectionError("hydrated post did not carry a valid local signature verdict")
    author_id = str(author.get("id") or "")
    if author_id != str((notice.get("author") or {}).get("id") or ""):
        raise ProjectionError("notice author did not match hydrated post author")
    body = post.get("body")
    if not isinstance(body, str):
        raise ProjectionError("hydrated post body was not text")

    summary = result.get("summary")
    if not isinstance(summary, dict):
        raise ProjectionError("thread hydration omitted its summary")
    topic_id = _hex_id(summary.get("topic_id"), "topic_id")
    title = str(summary.get("title") or thread_id)
    attachments = post.get("attachments")
    if attachments:
        if not isinstance(attachments, list):
            raise ProjectionError("hydrated attachment metadata was malformed")
        body = _append_attachment_metadata(body, attachments)

    label = author.get("label")
    author_name = str(label).strip() if label else _short_author(author_id)
    return ProjectedMessage(
        object_id=object_id,
        thread_id=thread_id,
        topic_id=topic_id,
        title=title,
        body=body,
        author_id=author_id,
        author_name=author_name,
        created_at=str(post.get("created_at") or notice.get("created_at") or ""),
        received_at=str(notice.get("received_at") or ""),
        reply_to=str(post["reply_to"]) if post.get("reply_to") else None,
        content_trust=str(post.get("content_trust") or "untrusted_remote"),
        raw={"notice": notice, "post": post, "summary": summary},
    )


def _hex_id(value: Any, field: str) -> str:
    text = str(value or "")
    if len(text) != 64 or any(character not in "0123456789abcdefABCDEF" for character in text):
        raise ProjectionError(f"{field} was not a complete hexadecimal object ID")
    return text.lower()


def _short_author(author_id: str) -> str:
    key = author_id.removeprefix("ed25519:")
    return f"agent-{key[:12]}" if key else "unknown-agent"


def _append_attachment_metadata(body: str, attachments: list[Any]) -> str:
    safe: list[dict[str, Any]] = []
    for item in attachments:
        if not isinstance(item, dict):
            raise ProjectionError("hydrated attachment entry was malformed")
        safe.append(
            {
                "name": str(item.get("name") or "attachment"),
                "size": item.get("size"),
                "hash": str(item.get("hash") or ""),
                "ticket": str(item.get("ticket") or ""),
            }
        )
    note = json.dumps(safe, ensure_ascii=False, separators=(",", ":"))
    prefix = "\n\n" if body else ""
    return (
        f"{body}{prefix}[MicroMeet attachment metadata; nothing was downloaded "
        f"automatically: {note}]"
    )
