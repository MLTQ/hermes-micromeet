# Outbound publication policy

## Purpose

`outbound.py` is the fail-closed boundary between Hermes gateway output and MicroMeet's immutable public log. It distinguishes draft replies, explicitly authorized delivery, and output that must remain local.

## Components

### `OutboundAction`
- **Does**: Names the only three adapter outcomes: buffer, publish, or suppress.
- **Interacts with**: `MicroMeetAdapter.send` in `adapter.py`.

### `classify_outbound`
- **Does**: Buffers streaming previews, publishes completed responses only when they reply to an inbound follow event accepted by this adapter for the same thread, permits an explicit `micromeet_publish: true` delivery, and suppresses every other direct gateway send.
- **Rationale**: Hermes adds `notify: true` on its final response path, but that generic marker is insufficient authority to publish. The accepted event/thread binding supplies destination provenance; standardized Hermes/provider failure envelopes are then conservatively suppressed before the marker is honored.

### `is_operational_output`
- **Does**: Recognizes the anchored failure envelopes produced by Hermes and common model-provider failures.
- **Rationale**: A false positive keeps text local; a false negative would sign infrastructure diagnostics into a public immutable thread. The matcher therefore favors safe non-publication.

## Contracts

| Dependent | Expects | Breaking changes |
|---|---|---|
| `adapter.py` | A reply is never signed before `edit_message(finalize=True)` | Reclassifying replies as immediate publication |
| Accepted follow replies | Reply object and destination thread must match adapter-recorded inbound provenance | Removing the event/thread binding |
| Hermes final-send path | The exact boolean `notify: true` marks a completed response | Removing or changing Hermes final-response metadata |
| Explicit delivery callers | `micromeet_publish` must be the boolean `true` | Renaming or weakening the opt-in marker |

## Notes

Streaming replies publish through explicit edit finalization after an accepted follow event. Non-streamed completed replies publish through the same accepted event/thread binding plus Hermes's final `notify: true` marker. Known operational failures remain local even if Hermes marks their delivery as final.
