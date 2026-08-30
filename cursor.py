"""Durable first-run and resume policy for the MicroMeet inbox cursor."""

from __future__ import annotations

from typing import Any

from .service import MicroMeetService

_CURSOR_KEY = "inbox_cursor"


class InboxCursor:
    """Read and commit one profile-local monotonic inbox position."""

    def __init__(
        self,
        *,
        state: Any,
        service: MicroMeetService,
        page_size: int,
        replay_existing: bool,
    ) -> None:
        self.state = state
        self.service = service
        self.page_size = page_size
        self.replay_existing = replay_existing

    async def starting(self) -> int:
        saved = self.state.get(_CURSOR_KEY, None)
        if isinstance(saved, int) and saved >= 0:
            return saved
        cursor = 0 if self.replay_existing else await self._latest()
        self.commit(cursor)
        return cursor

    def commit(self, cursor: int) -> None:
        if not isinstance(cursor, int) or cursor < 0:
            raise ValueError("MicroMeet inbox cursor must be a non-negative integer")
        self.state.set(_CURSOR_KEY, cursor)

    async def _latest(self) -> int:
        cursor = 0
        for _ in range(1_000):
            response = await self.service.run(
                [
                    "inbox",
                    "--cursor",
                    str(cursor),
                    "--limit",
                    str(self.page_size),
                ]
            )
            if not response.get("ok"):
                error = response.get("error") or {}
                raise RuntimeError(str(error.get("message") or "inbox read failed"))
            result = response.get("result") or {}
            items = result.get("items") or []
            next_cursor = result.get("next_cursor")
            if not items or not isinstance(next_cursor, int) or next_cursor <= cursor:
                return cursor
            cursor = next_cursor
        raise RuntimeError("inbox cursor scan exceeded its bounded page count")
