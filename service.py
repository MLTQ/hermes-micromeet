"""Supervise the local MicroMeet daemon and JSON Lines inbox watcher."""

from __future__ import annotations

import asyncio
import json
from collections import deque
from collections.abc import AsyncIterator
from typing import Any

from .messages import ProjectionError
from .runner import MmClient, RuntimeSettings


class ServiceError(RuntimeError):
    """A long-lived MicroMeet child process violated its lifecycle contract."""


class MicroMeetService:
    """Own subprocess lifecycle while leaving message routing to the adapter."""

    def __init__(self, settings: RuntimeSettings):
        self.settings = settings
        self.client = MmClient(settings)
        self._watch_process: asyncio.subprocess.Process | None = None
        self._daemon_process: asyncio.subprocess.Process | None = None
        self._stderr_tasks: set[asyncio.Task] = set()
        self._diagnostics: deque[str] = deque(maxlen=20)

    async def run(
        self,
        arguments: list[str],
        *,
        stdin: str | None = None,
    ) -> dict[str, Any]:
        return await asyncio.to_thread(self.client.run, arguments, stdin=stdin)

    async def ensure_status(self) -> dict[str, Any]:
        """Attach to a running daemon or start one when policy allows."""
        status = await self.run(["status"])
        code = str((status.get("error") or {}).get("code") or "")
        if status.get("ok") or code != "daemon_unavailable" or not self.settings.autostart:
            return status
        status = await self._start_daemon()
        if not status.get("ok"):
            await self.stop_owned_daemon()
        return status

    async def start_watcher(self, cursor: int) -> None:
        if self._watch_process and self._watch_process.returncode is None:
            raise ServiceError("MicroMeet inbox watcher is already running")
        command = [
            "inbox",
            "--cursor",
            str(cursor),
            "--limit",
            str(self.settings.inbox_page_size),
            "watch",
            "--poll-ms",
            str(self.settings.watch_poll_ms),
        ]
        self._watch_process = await asyncio.create_subprocess_exec(
            *self.client.command(command),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._track_stderr(self._watch_process, "watch")

    async def notices(self) -> AsyncIterator[dict[str, Any]]:
        """Yield verified local notice envelopes from the active watcher."""
        process = self._watch_process
        if process is None or process.stdout is None:
            raise ServiceError("MicroMeet inbox watcher was not started")
        while True:
            line = await process.stdout.readline()
            if not line:
                await process.wait()
                raise ServiceError(f"MicroMeet inbox watcher exited{self.diagnostic_suffix()}")
            if len(line) > 1_048_576:
                raise ProjectionError("watch notice exceeded the 1 MiB line limit")
            try:
                envelope = json.loads(line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ProjectionError(f"watcher emitted invalid JSON: {exc}") from exc
            if not isinstance(envelope, dict) or envelope.get("ok") is not True:
                error = envelope.get("error") if isinstance(envelope, dict) else None
                raise ProjectionError(
                    str((error or {}).get("message") or "watcher emitted an error envelope")
                )
            notice = envelope.get("result")
            if not isinstance(notice, dict):
                raise ProjectionError("watcher notice omitted its result object")
            yield notice

    async def stop(self) -> None:
        await self.stop_watcher()
        await self.stop_owned_daemon()
        for task in tuple(self._stderr_tasks):
            task.cancel()
        if self._stderr_tasks:
            await asyncio.gather(*self._stderr_tasks, return_exceptions=True)
        self._stderr_tasks.clear()

    async def stop_watcher(self) -> None:
        process = self._watch_process
        self._watch_process = None
        await self._stop_process(process)

    async def stop_owned_daemon(self) -> None:
        process = self._daemon_process
        self._daemon_process = None
        await self._stop_process(process)

    async def _start_daemon(self) -> dict[str, Any]:
        if not self.client.binary_available():
            return MmClient.failure(
                "binary_not_found",
                f"MicroMeet executable was not found: {self.settings.executable}",
            )
        self._daemon_process = await asyncio.create_subprocess_exec(
            *self.client.command(["serve"], json_output=False),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        self._track_stderr(self._daemon_process, "daemon")
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.settings.startup_timeout
        while loop.time() < deadline:
            if self._daemon_process.returncode is not None:
                return MmClient.failure(
                    "daemon_exited",
                    f"MicroMeet daemon exited during startup{self.diagnostic_suffix()}",
                )
            status = await self.run(["status"])
            if status.get("ok"):
                return status
            await asyncio.sleep(0.2)
        return MmClient.failure(
            "startup_timeout",
            f"MicroMeet daemon did not become ready in {self.settings.startup_timeout:g}s",
        )

    def _track_stderr(self, process: asyncio.subprocess.Process, label: str) -> None:
        if process.stderr is None:
            return
        task = asyncio.create_task(self._drain_stderr(process.stderr, label))
        self._stderr_tasks.add(task)
        task.add_done_callback(self._stderr_tasks.discard)

    async def _drain_stderr(self, stream: asyncio.StreamReader, label: str) -> None:
        while True:
            line = await stream.readline()
            if not line:
                return
            text = line.decode("utf-8", errors="replace").strip()
            if text:
                self._diagnostics.append(f"{label}: {text[:500]}")

    @staticmethod
    async def _stop_process(process: asyncio.subprocess.Process | None) -> None:
        if process is None or process.returncode is not None:
            return
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=5.0)
        except TimeoutError:
            process.kill()
            await process.wait()

    def diagnostic_suffix(self) -> str:
        return f": {self._diagnostics[-1]}" if self._diagnostics else ""
