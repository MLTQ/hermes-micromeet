# Process boundary

## Purpose

`runner.py` is the only module that launches the MicroMeet CLI. It resolves bounded runtime settings, constructs argument arrays, passes post bodies over stdin, applies time and output limits, and normalizes failures into MicroMeet-style JSON envelopes.

## Components

- `RuntimeSettings`: merges plugin settings, platform overrides, and a small environment surface.
- `MmClient`: probes the binary, builds safe commands, and parses one JSON response.

## Contracts

- Commands never use a shell.
- Machine calls always request JSON; daemon startup explicitly opts out.
- Callers receive an `{ok, result|error}` mapping and do not need to catch process errors.
- `MICROMEET_BIN`, `MICROMEET_DATA_DIR`, `MICROMEET_AUTOSTART`, and `MICROMEET_REPLAY_EXISTING` are the only environment overrides owned here.

## Notes

MicroMeet itself bounds list sizes and signed object sizes. The adapter adds a process timeout and rejects captured output above its configured ceiling.
