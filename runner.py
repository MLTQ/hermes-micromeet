"""Safe, bounded process boundary for the MicroMeet JSON CLI."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Iterable


def _as_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    token = str(value).strip().lower()
    if token in {"1", "true", "yes", "on"}:
        return True
    if token in {"0", "false", "no", "off"}:
        return False
    return default


def _as_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return min(max(parsed, minimum), maximum)


def _as_float(value: Any, default: float, minimum: float, maximum: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    if parsed != parsed:  # NaN
        return default
    return min(max(parsed, minimum), maximum)


@dataclass(frozen=True)
class RuntimeSettings:
    """Resolved settings shared by tools and the gateway adapter."""

    executable: str = "mm"
    data_dir: str | None = None
    command_timeout: float = 30.0
    max_output_bytes: int = 16 * 1024 * 1024
    autostart: bool = True
    startup_timeout: float = 20.0
    watch_poll_ms: int = 1_000
    inbox_page_size: int = 100
    replay_existing: bool = False

    @classmethod
    def from_context(cls, ctx: Any) -> "RuntimeSettings":
        """Load namespaced plugin settings, with environment overrides."""
        get = ctx.get_config
        settings = cls(
            executable=str(get("binary", "mm") or "mm"),
            data_dir=str(get("data_dir")) if get("data_dir") else None,
            command_timeout=_as_float(get("command_timeout", 30), 30.0, 1.0, 300.0),
            max_output_bytes=_as_int(
                get("max_output_bytes", 16 * 1024 * 1024),
                16 * 1024 * 1024,
                1_048_576,
                64 * 1024 * 1024,
            ),
            autostart=_as_bool(get("autostart", True), True),
            startup_timeout=_as_float(get("startup_timeout", 20), 20.0, 1.0, 120.0),
            watch_poll_ms=_as_int(get("watch_poll_ms", 1_000), 1_000, 100, 60_000),
            inbox_page_size=_as_int(get("inbox_page_size", 100), 100, 1, 100),
            replay_existing=_as_bool(get("replay_existing", False), False),
        )
        return settings.with_environment()

    def for_platform(self, config: Any) -> "RuntimeSettings":
        """Apply gateway platform ``extra`` values, then environment values."""
        extra = getattr(config, "extra", {}) or {}
        updated = replace(
            self,
            executable=str(extra.get("binary", self.executable) or self.executable),
            data_dir=(
                str(extra["data_dir"])
                if extra.get("data_dir")
                else self.data_dir
            ),
            command_timeout=_as_float(
                extra.get("command_timeout"), self.command_timeout, 1.0, 300.0
            ),
            autostart=_as_bool(extra.get("autostart"), self.autostart),
            startup_timeout=_as_float(
                extra.get("startup_timeout"), self.startup_timeout, 1.0, 120.0
            ),
            watch_poll_ms=_as_int(
                extra.get("watch_poll_ms"), self.watch_poll_ms, 100, 60_000
            ),
            inbox_page_size=_as_int(
                extra.get("inbox_page_size"), self.inbox_page_size, 1, 100
            ),
            replay_existing=_as_bool(
                extra.get("replay_existing"), self.replay_existing
            ),
        )
        return updated.with_environment()

    def with_environment(self) -> "RuntimeSettings":
        """Apply the small operator-facing environment override surface."""
        return replace(
            self,
            executable=os.getenv("MICROMEET_BIN") or self.executable,
            data_dir=os.getenv("MICROMEET_DATA_DIR") or self.data_dir,
            autostart=_as_bool(os.getenv("MICROMEET_AUTOSTART"), self.autostart),
            replay_existing=_as_bool(
                os.getenv("MICROMEET_REPLAY_EXISTING"), self.replay_existing
            ),
        )


class MmClient:
    """Invoke ``mm`` without a shell and return its stable JSON envelope."""

    def __init__(self, settings: RuntimeSettings):
        self.settings = settings

    def command(self, arguments: Iterable[str], *, json_output: bool = True) -> list[str]:
        argv = [self.settings.executable]
        if json_output:
            argv.append("--json")
        if self.settings.data_dir:
            argv.extend(["--data-dir", self.settings.data_dir])
        argv.extend(str(value) for value in arguments)
        if any("\0" in value for value in argv):
            raise ValueError("MicroMeet arguments may not contain NUL bytes")
        return argv

    def binary_available(self) -> bool:
        executable = self.settings.executable
        if os.sep in executable or (os.altsep and os.altsep in executable):
            path = Path(executable).expanduser()
            return path.is_file() and os.access(path, os.X_OK)
        return shutil.which(executable) is not None

    def run(
        self,
        arguments: Iterable[str],
        *,
        stdin: str | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        try:
            completed = subprocess.run(
                self.command(arguments),
                input=stdin.encode("utf-8") if stdin is not None else None,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=timeout or self.settings.command_timeout,
                shell=False,
            )
        except FileNotFoundError:
            return self.failure(
                "binary_not_found",
                f"MicroMeet executable was not found: {self.settings.executable}",
            )
        except subprocess.TimeoutExpired:
            return self.failure("timeout", "MicroMeet command timed out")
        except (OSError, ValueError) as exc:
            return self.failure("process_error", f"MicroMeet could not be started: {exc}")

        if len(completed.stdout) > self.settings.max_output_bytes:
            return self.failure("output_too_large", "MicroMeet JSON output exceeded the configured limit")
        stderr = completed.stderr[:8_192].decode("utf-8", errors="replace").strip()
        try:
            payload = json.loads(completed.stdout.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            detail = f"; stderr: {stderr}" if stderr else ""
            return self.failure("invalid_json", f"MicroMeet returned invalid JSON: {exc}{detail}")
        if not isinstance(payload, dict) or not isinstance(payload.get("ok"), bool):
            return self.failure("invalid_response", "MicroMeet returned an invalid response envelope")
        if completed.returncode != 0 and payload.get("ok") is True:
            detail = f": {stderr}" if stderr else ""
            return self.failure("process_failed", f"MicroMeet exited with status {completed.returncode}{detail}")
        return payload

    @staticmethod
    def failure(code: str, message: str) -> dict[str, Any]:
        return {"ok": False, "error": {"code": code, "message": message}}
