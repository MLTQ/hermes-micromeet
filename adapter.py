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
    ProjectionError,
    ProjectedMessage,
    project_notice,
)
from .runner import RuntimeSettings
from .service import MicroMeetService

logger = logging.getLogger(__name__)


class MicroMeetAdapter(BasePlatformAdapter):
    """Map one MicroMeet thread to one Hermes chat session."""

    supports_code_blocks = True
    REQUIRES_EDIT_FINALIZE = True

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

        identity = ((status.get("result") or {}).get("identity") or {})
        self._own_author_id = str(identity.get("author_id") or "")
        if not self._own_author_id:
            await self.service.stop_owned_daemon()
            self._set_fatal_error(
                "micromeet_identity_missing",
                "MicroMeet status omitted the local author identity",
                retryable=False,
            )
            return False

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

        self._watch_task = asyncio.create_task(
            self._watch_loop(), name="hermes-micromeet-inbox"
        )
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
        if (metadata or {}).get("expect_edits"):
            self._draft_sequence += 1
            draft_id = f"micromeet-draft:{self._draft_sequence}"
            self._drafts[draft_id] = (str(chat_id), content, reply_to, metadata)
            return SendResult(success=True, message_id=draft_id)
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
        result = await self._publish(original_chat, content, reply_to, metadata)
        if result.success:
            self._drafts.pop(str(message_id), None)
        return result

    async def get_chat_info(self, chat_id: str) -> dict[str, Any]:
        response = await self.service.run(
            ["thread", "read", str(chat_id), "--limit", "1"]
        )
        if not response.get("ok"):
            return {"name": str(chat_id), "type": "group"}
        summary = ((response.get("result") or {}).get("summary") or {})
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
                retryable=code
                in {"daemon_unavailable", "internal", "timeout", "process_error"},
                raw_response=response,
            )
        result = response.get("result") or {}
        message_id = result.get("id") or result.get("object_id")
        return SendResult(
            success=True,
            message_id=str(message_id or ""),
            raw_response=response,
        )

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
        await self.handle_message(self._event(projected))
        self.cursor.commit(cursor)

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
        return MessageEvent(
            text=message.body,
            message_type=MessageType.TEXT,
            user_id=message.author_id,
            user_name=message.author_name,
            source=source,
            raw_message=message.raw,
            message_id=message.object_id,
            reply_to_message_id=message.reply_to,
            timestamp=_timestamp(message.created_at),
            allow_gateway_control=False,
            metadata={
                "micromeet_content_trust": message.content_trust,
                "micromeet_topic_id": message.topic_id,
            },
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
        retry_bucket = "" if stable_reply else str(int(time.time() // 300))
        digest = hashlib.sha256(
            "\0".join(
                [str(chat_id), content, str(stable_reply or ""), retry_bucket]
            ).encode("utf-8")
        ).hexdigest()
        return f"hermes:{digest}"


def _timestamp(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return datetime.now()
