# Test bootstrap

## Purpose

`bootstrap.py` loads the repository root under a stable synthetic package name, allowing relative imports to behave exactly as they do after Hermes installs the plugin.

## Components

- `load_module`: loads an isolated module without executing plugin registration imports.
- `load_plugin`: executes the real root entry point and optionally adds a local Hermes source tree for integration tests.

## Contracts

- Tests do not require pip installation or mutate the user's Hermes profile.
- `HERMES_AGENT_SOURCE` is test-only and optional.

## Notes

The repository directory contains a hyphen, which is a valid Hermes plugin name but not a normal Python import identifier; the synthetic package avoids coupling tests to installation internals.
