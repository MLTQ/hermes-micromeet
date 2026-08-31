"""Tests for safe MicroMeet process invocation."""

from __future__ import annotations

import subprocess
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from bootstrap import load_module

runner = load_module("runner")


class RunnerTests(unittest.TestCase):
    def test_context_bridge_defaults_on_with_bounded_context(self) -> None:
        context = SimpleNamespace(get_config=lambda _key, default=None: default)
        with patch.dict("os.environ", {}, clear=True):
            settings = runner.RuntimeSettings.from_context(context)
        self.assertTrue(settings.context_bridge)
        self.assertEqual(settings.context_bridge_max_chars, 6_000)

    def test_context_bridge_environment_override(self) -> None:
        with patch.dict("os.environ", {"MICROMEET_CONTEXT_BRIDGE": "false"}, clear=True):
            settings = runner.RuntimeSettings().with_environment()
        self.assertFalse(settings.context_bridge)

    def test_notifications_default_on_and_allow_platform_override(self) -> None:
        context = SimpleNamespace(get_config=lambda _key, default=None: default)
        with patch.dict("os.environ", {}, clear=True):
            defaults = runner.RuntimeSettings.from_context(context)
            disabled = defaults.for_platform(SimpleNamespace(extra={"notifications": False}))
        self.assertTrue(defaults.notifications)
        self.assertFalse(disabled.notifications)

    def test_notifications_environment_override(self) -> None:
        with patch.dict("os.environ", {"MICROMEET_NOTIFICATIONS": "false"}, clear=True):
            settings = runner.RuntimeSettings().with_environment()
        self.assertFalse(settings.notifications)

    def test_command_uses_global_json_and_data_dir_options(self) -> None:
        settings = runner.RuntimeSettings(executable="/opt/mm", data_dir="/tmp/mm-data")
        client = runner.MmClient(settings)
        self.assertEqual(
            client.command(["post", "thread", "--stdin"]),
            ["/opt/mm", "--json", "--data-dir", "/tmp/mm-data", "post", "thread", "--stdin"],
        )

    @patch.object(subprocess, "run")
    def test_body_is_passed_as_exact_stdin_without_a_shell(self, run_mock) -> None:
        run_mock.return_value = SimpleNamespace(
            stdout=b'{"ok":true,"result":{"id":"abc"}}', stderr=b"", returncode=0
        )
        client = runner.MmClient(runner.RuntimeSettings())
        body = '$(touch /tmp/nope) `quoted` "text"'
        result = client.run(["post", "thread", "--stdin"], stdin=body)
        self.assertTrue(result["ok"])
        kwargs = run_mock.call_args.kwargs
        self.assertEqual(kwargs["input"], body.encode("utf-8"))
        self.assertIs(kwargs["shell"], False)

    @patch.object(subprocess, "run")
    def test_invalid_json_is_a_structured_failure(self, run_mock) -> None:
        run_mock.return_value = SimpleNamespace(stdout=b"not-json", stderr=b"detail", returncode=1)
        result = runner.MmClient(runner.RuntimeSettings()).run(["status"])
        self.assertEqual(result["error"]["code"], "invalid_json")

    @patch.object(subprocess, "run", side_effect=subprocess.TimeoutExpired("mm", 1))
    def test_timeout_is_a_structured_failure(self, _run_mock) -> None:
        result = runner.MmClient(runner.RuntimeSettings()).run(["status"])
        self.assertEqual(result["error"]["code"], "timeout")


if __name__ == "__main__":
    unittest.main()
