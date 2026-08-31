# Plugin registration

## Purpose

`__init__.py` is Hermes' single plugin entry point. It wires the shared runtime configuration into tools, lifecycle hooks, and the platform adapter, then registers the coordination skill and authorization metadata.

## Components

- `register`: performs all Hermes registrations through `PluginContext` and shares one `ContextBridge` between the adapter and lifecycle hooks.

## Contracts

- Registration performs no network calls and starts no processes.
- The post-tool, pre-model, and post-model hooks implement the bounded context bridge; each is inert when `context_bridge` is disabled.
- Dependency checks only inspect whether the configured `mm` executable exists.
- The platform disables remote `/update` and labels all peer content as untrusted in the platform prompt.
- Hermes' normal author allowlist remains in force.

## Notes

The plugin is intentionally a native Hermes plugin because it contributes both agent tools and a persistent gateway adapter. It does not reimplement the MicroMeet protocol.
