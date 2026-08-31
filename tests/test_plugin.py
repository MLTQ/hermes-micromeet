"""Integration tests for the Hermes plugin registration surface."""

from __future__ import annotations

import unittest

from bootstrap import load_plugin


class FakeState:
    def get(self, _key, default=None):
        return default

    def set(self, _key, _value) -> None:
        return None


class FakeContext:
    def __init__(self) -> None:
        self.tools = []
        self.skills = []
        self.platforms = []
        self.hooks = []
        self.state = FakeState()

    def get_config(self, _key, default=None):
        return default

    def register_tool(self, **kwargs) -> None:
        self.tools.append(kwargs)

    def register_skill(self, **kwargs) -> None:
        self.skills.append(kwargs)

    def register_platform(self, **kwargs) -> None:
        self.platforms.append(kwargs)

    def register_hook(self, name, callback) -> None:
        self.hooks.append((name, callback))


class PluginTests(unittest.TestCase):
    def test_root_registers_tools_skill_and_platform(self) -> None:
        plugin = load_plugin()
        context = FakeContext()
        plugin.register(context)
        self.assertEqual(len(context.tools), 10)
        self.assertEqual(
            [name for name, _callback in context.hooks],
            ["post_tool_call", "pre_llm_call", "post_llm_call"],
        )
        self.assertEqual(context.skills[0]["name"], "micromeet-coordinate")
        platform = context.platforms[0]
        self.assertEqual(platform["name"], "micromeet")
        self.assertEqual(platform["allowed_users_env"], "MICROMEET_ALLOWED_AUTHORS")
        self.assertFalse(platform["allow_update_command"])


if __name__ == "__main__":
    unittest.main()
