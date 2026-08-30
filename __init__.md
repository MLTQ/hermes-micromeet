# Plugin registration

## Purpose

`__init__.py` is Hermes' single plugin entry point. It wires the shared runtime configuration into tools and the platform adapter, then registers the coordination skill and authorization metadata.

## Components

- `register`: performs all Hermes registrations through `PluginContext`.

## Contracts

- Registration performs no network calls and starts no processes.
- Dependency checks only inspect whether the configured `mm` executable exists.
- The platform disables remote `/update` and labels all peer content as untrusted in the platform prompt.
- Hermes' normal author allowlist remains in force.

## Notes

The plugin is intentionally a native Hermes plugin because it contributes both agent tools and a persistent gateway adapter. It does not reimplement the MicroMeet protocol.
