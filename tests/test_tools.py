"""Tests for focused Hermes tool handlers and registration."""

from __future__ import annotations

import json
import unittest
from types import SimpleNamespace

from bootstrap import load_module

tools_module = load_module("tools")


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[list[str], str | None, float | None]] = []
        self.settings = SimpleNamespace(command_timeout=30.0)

    def run(self, command, *, stdin=None, timeout=None):
        self.calls.append((list(command), stdin, timeout))
        return {"ok": True, "result": {"command": list(command)}}


class FakeContext:
    def __init__(self) -> None:
        self.names: list[str] = []

    def register_tool(self, **kwargs) -> None:
        self.names.append(kwargs["name"])


class ToolTests(unittest.TestCase):
    def test_post_uses_stdin_and_repeated_attachment_arguments(self) -> None:
        client = FakeClient()
        handler = tools_module.build_handlers(client)["micromeet_post"]
        response = json.loads(
            handler(
                {
                    "thread_id": "a" * 64,
                    "body": "hello\npeer",
                    "attachments": ["/tmp/a", "/tmp/b"],
                    "idempotency_key": "run:1",
                }
            )
        )
        self.assertTrue(response["ok"])
        command, stdin, _timeout = client.calls[0]
        self.assertEqual(stdin, "hello\npeer")
        self.assertEqual(command.count("--attach"), 2)
        self.assertNotIn("hello\npeer", command)

    def test_registration_matches_declared_tool_catalog(self) -> None:
        context = FakeContext()
        tools_module.register_tools(context, FakeClient())
        self.assertEqual(set(context.names), set(tools_module.TOOLS))
        self.assertEqual(len(context.names), 10)


if __name__ == "__main__":
    unittest.main()
