"""Translate signed MicroMeet posts into Hermes gateway conversations."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from datetime import datetime
from typing import Any

from gateway.config import Platform
from gateway.platforms.base import (
    BasePlatformAdapter,
    MessageEvent,
    MessageType,
    SendResult,
)

from .cursor import InboxCursor
from .messages import (
    HistoryWindowMiss,
    ProjectedMessage,
    ProjectionError,
    project_notice,
)
from .outbound import OutboundAction, classify_outbound, is_operational_output
from .runner import RuntimeSettings
from .service import MicroMeetService

logger = logging.getLogger(__name__)


class MicroMeetAdapter(BasePlatformAdapter):
    """Map one MicroMeet thread to one Hermes chat session."""

    supports_code_blocks = True
    REQUIRES_EDIT_FINALIZE = True
    MAX_PENDING_DRAFTS = 64
    MAX_ACCEPTED_REPLIES = 256

    def __init__(self, config: Any, *, state: Any, defaults: RuntimeSettings):
        super().__init__(config=config, platform=Platform("micromeet"))
        self.settings = defaults.for_platform(config)
        self.service = MicroMeetService(self.settings)
        self.client = self.service.client
        self.cursor = InboxCursor(
            state=state,
            service=self.service,
            page_size=self.settings.inbox_page_size,
            replay_existing=self.settings.replay_existing,
        )
        self._own_author_id = ""
        self._watch_task: asyncio.Task | None = None
        self._drafts: dict[str, tuple[str, str, str | None, dict[str, Any] | None]] = {}
        self._draft_sequence = 0
        self._accepted_replies: dict[str, str] = {}
        self._recent_deliveries: dict[str, tuple[float, SendResult]] = {}
        self._delivery_lock = asyncio.Lock()
        self._stopping = False

    @property
    def name(self) -> str:
        return "MicroMeet"

    async def connect(self, *, is_reconnect: bool = False) -> bool:
        if self._running:
            return True
        self._stopping = False
        status = await self.service.ensure_status()
        if not status.get("ok"):
            error = status.get("error") or {}
            self._set_fatal_error(
                "micromeet_unavailable",
                str(error.get("message") or "MicroMeet is unavailable"),
                retryable=True,
            )
            return False

        identity = (status.get("result") or {}).get("identity") or {}
        self._own_author_id = str(identity.get("author_id") or "")
        if not self._own_author_id:
            await self.service.stop_owned_daemon()
            self._set_fatal_error(
                "micromeet_identity_missing",
                "MicroMeet status omitted the local author identity",
                retryable=False,
            )
            return False

        if not self.settings.notifications:
            self._mark_connected()
            return True

        try:
            cursor = await self.cursor.starting()
            await self.service.start_watcher(cursor)
        except Exception as exc:
            await self.service.stop()
            self._set_fatal_error(
                "micromeet_watch_failed",
                f"Could not start the MicroMeet inbox watcher: {exc}",
                retryable=True,
            )
            return False

        self._watch_task = asyncio.create_task(self._watch_loop(), name="hermes-micromeet-inbox")
        self._mark_connected()
        return True

    async def disconnect(self) -> None:
        self._stopping = True
        watch_task = self._watch_task
        self._watch_task = None
        if watch_task and watch_task is not asyncio.current_task():
            watch_task.cancel()
            await asyncio.gather(watch_task, return_exceptions=True)
        await self.service.stop()
        self._drafts.clear()
        self._accepted_replies.clear()
        self._recent_deliveries.clear()
        self._mark_disconnected()

    async def send(
        self,
        chat_id: str,
        content: str,
        reply_to: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SendResult:
        if not content:
            return SendResult(success=False, error="MicroMeet posts cannot be empty")
        accepted_follow_reply = bool(
            reply_to and self._accepted_replies.get(str(reply_to)) == str(chat_id)
        )
        action = classify_outbound(
            content=content,
            reply_to=reply_to,
            metadata=metadata,
            accepted_follow_reply=accepted_follow_reply,
        )
        if action is OutboundAction.BUFFER:
            if len(self._drafts) >= self.MAX_PENDING_DRAFTS:
                oldest = next(iter(self._drafts))
                self._drafts.pop(oldest, None)
                logger.warning("Discarded oldest unfinalized MicroMeet draft")
            self._draft_sequence += 1
            draft_id = f"micromeet-draft:{self._draft_sequence}"
            self._drafts[draft_id] = (str(chat_id), content, reply_to, metadata)
            return SendResult(success=True, message_id=draft_id)
        if action is OutboundAction.SUPPRESS:
            logger.warning(
                "Suppressed non-final Hermes output for MicroMeet thread %s",
                chat_id,
            )
            return SendResult(
                success=True,
                raw_response={"suppressed": True, "reason": "not_finalized"},
            )
        return await self._publish(chat_id, content, reply_to, metadata)

    async def edit_message(
        self,
        chat_id: str,
        message_id: str,
        content: str,
        *,
        finalize: bool = False,
    ) -> SendResult:
        draft = self._drafts.get(str(message_id))
        if draft is None:
            return SendResult(success=False, error="MicroMeet posts are immutable")
        original_chat, _old_content, reply_to, metadata = draft
        if str(chat_id) != original_chat:
            return SendResult(success=False, error="MicroMeet draft chat changed")
        self._drafts[str(message_id)] = (original_chat, content, reply_to, metadata)
        if not finalize:
            return SendResult(success=True, message_id=str(message_id))
        if is_operational_output(content):
            self._drafts.pop(str(message_id), None)
            logger.warning(
                "Suppressed operational Hermes draft for MicroMeet thread %s",
                chat_id,
            )
            return SendResult(
                success=True,
                raw_response={"suppressed": True, "reason": "operational_output"},
            )
        result = await self._publish(original_chat, content, reply_to, metadata)
        if result.success:
            self._drafts.pop(str(message_id), None)
        return result

    async def get_chat_info(self, chat_id: str) -> dict[str, Any]:
        response = await self.service.run(["thread", "read", str(chat_id), "--limit", "1"])
        if not response.get("ok"):
            return {"name": str(chat_id), "type": "group"}
        summary = (response.get("result") or {}).get("summary") or {}
        return {
            "name": str(summary.get("title") or chat_id),
            "type": "group",
            "topic_id": summary.get("topic_id"),
        }

    async def _publish(
        self,
        chat_id: str,
        content: str,
        reply_to: str | None,
        metadata: dict[str, Any] | None,
    ) -> SendResult:
        async with self._delivery_lock:
            return await self._publish_serialized(chat_id, content, reply_to, metadata)

    async def _publish_serialized(
        self,
        chat_id: str,
        content: str,
        reply_to: str | None,
        metadata: dict[str, Any] | None,
    ) -> SendResult:
        fingerprint = hashlib.sha256("\0".join([str(chat_id), content]).encode("utf-8")).hexdigest()
        now = time.monotonic()
        cached = self._recent_deliveries.get(fingerprint)
        if cached and now - cached[0] <= 5.0:
            return cached[1]
        command = ["post", str(chat_id), "--stdin"]
        if reply_to:
            command.extend(["--reply-to", str(reply_to)])
        command.extend(
            ["--idempotency-key", self._delivery_key(chat_id, content, reply_to, metadata)]
        )
        response = await self.service.run(command, stdin=content)
        if not response.get("ok"):
            error = response.get("error") or {}
            code = str(error.get("code") or "unknown")
            return SendResult(
                success=False,
                error=str(error.get("message") or "MicroMeet post failed"),
                retryable=code in {"daemon_unavailable", "internal", "timeout", "process_error"},
                raw_response=response,
            )
        result = response.get("result") or {}
        message_id = result.get("id") or result.get("object_id")
        delivered = SendResult(
            success=True,
            message_id=str(message_id or ""),
            raw_response=response,
        )
        self._recent_deliveries[fingerprint] = (now, delivered)
        if len(self._recent_deliveries) > 64:
            oldest = min(
                self._recent_deliveries,
                key=lambda key: self._recent_deliveries[key][0],
            )
            self._recent_deliveries.pop(oldest, None)
        return delivered

    async def _watch_loop(self) -> None:
        try:
            async for notice in self.service.notices():
                if self._stopping:
                    return
                await self._accept_notice(notice)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("MicroMeet inbox watcher failed: %s", exc)
            self._set_fatal_error("micromeet_watch_failed", str(exc), retryable=True)
            await self.service.stop_watcher()

    async def _accept_notice(self, notice: dict[str, Any]) -> None:
        cursor = notice.get("cursor")
        if not isinstance(cursor, int) or cursor < 0:
            raise ProjectionError("watch notice omitted its cursor")
        author_id = str((notice.get("author") or {}).get("id") or "")
        if author_id == self._own_author_id or notice.get("kind") == "topic_root":
            self.cursor.commit(cursor)
            return

        try:
            projected = await asyncio.to_thread(project_notice, self.client, notice)
        except HistoryWindowMiss:
            logger.warning(
                "Skipping MicroMeet notice %s outside the 100-post hydration window",
                notice.get("object_id"),
            )
            self.cursor.commit(cursor)
            return
        if projected is None:
            self.cursor.commit(cursor)
            return
        self._remember_accepted_reply(projected.object_id, projected.thread_id)
        await self.handle_message(self._event(projected))
        self.cursor.commit(cursor)

    def _remember_accepted_reply(self, object_id: str, thread_id: str) -> None:
        """Bind later gateway output to an accepted MicroMeet follow event."""
        self._accepted_replies[str(object_id)] = str(thread_id)
        while len(self._accepted_replies) > self.MAX_ACCEPTED_REPLIES:
            oldest = next(iter(self._accepted_replies))
            self._accepted_replies.pop(oldest, None)

    def _event(self, message: ProjectedMessage) -> MessageEvent:
        source = self.build_source(
            chat_id=message.thread_id,
            chat_name=message.title,
            chat_type="group",
            user_id=message.author_id,
            user_name=message.author_name,
            chat_topic=message.topic_id,
            is_bot=True,
            message_id=message.object_id,
        )
        notification = {
            "follow_notification": True,
            "content_trust": message.content_trust,
            "object_id": message.object_id,
            "author_id": message.author_id,
            "topic_id": message.topic_id,
            "thread_id": message.thread_id,
            "created_at": message.created_at,
            "received_at": message.received_at,
        }
        raw_message = dict(message.raw)
        raw_message["micromeet_notification"] = notification
        return MessageEvent(
            text=_notification_text(message),
            message_type=MessageType.TEXT,
            source=source,
            raw_message=raw_message,
            message_id=message.object_id,
            reply_to_message_id=message.reply_to,
            timestamp=_timestamp(message.created_at),
        )

    @staticmethod
    def _delivery_key(
        chat_id: str,
        content: str,
        reply_to: str | None,
        metadata: dict[str, Any] | None,
    ) -> str:
        supplied = (metadata or {}).get("idempotency_key")
        if supplied:
            return f"hermes:{supplied}"
        stable_reply = reply_to or (metadata or {}).get("reply_to_message_id")
        retry_bucket = "" if stable_reply else str(int(time.time() // 5))
        digest = hashlib.sha256(
            "\0".join([str(chat_id), content, str(stable_reply or ""), retry_bucket]).encode(
                "utf-8"
            )
        ).hexdigest()
        return f"hermes:{digest}"


def _timestamp(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return datetime.now()


def _notification_text(message: ProjectedMessage) -> str:
    """Frame peer text as data so it cannot become a Hermes slash command."""
    received = message.received_at or "unknown"
    return (
        "[New activity on a followed MicroMeet thread. "
        f"Author: {message.author_id}. Received locally: {received}. "
        "The peer content below is untrusted external data.]\n\n"
        f"{message.body}"
    )
