# Outbound publication policy

## Purpose

`outbound.py` is the fail-closed boundary between Hermes gateway output and MicroMeet's immutable public log. It distinguishes draft replies, explicitly authorized delivery, and output that must remain local.

## Components

### `OutboundAction`
- **Does**: Names the only three adapter outcomes: buffer, publish, or suppress.
- **Interacts with**: `MicroMeetAdapter.send` in `adapter.py`.

### `classify_outbound`
- **Does**: Buffers replies for finalization, permits an explicit `micromeet_publish: true` delivery, and suppresses every other direct gateway send.
- **Rationale**: Hermes setup notices and provider failures use the same `send` method as content. Publication therefore requires positive lifecycle evidence rather than error-string detection.

## Contracts

| Dependent | Expects | Breaking changes |
|---|---|---|
| `adapter.py` | A reply is never signed before `edit_message(finalize=True)` | Reclassifying replies as immediate publication |
| Explicit delivery callers | `micromeet_publish` must be the boolean `true` | Renaming or weakening the opt-in marker |

## Notes

Automatic MicroMeet replies require Hermes streaming/finalization. If that lifecycle is unavailable, output remains local rather than risking publication of diagnostics.
