# Registration tests

## Purpose

`test_plugin.py` exercises the real root entry point against a minimal implementation of Hermes' public `PluginContext` surface.

## Contracts tested

- One registration call exposes ten tools, one skill, one platform, and the three bounded-context lifecycle hooks.
- The platform uses the dedicated author allowlist and cannot receive `/update` authority.

## Notes

Set `HERMES_AGENT_SOURCE` when running outside an installed Hermes environment so the adapter can import the public gateway types.
