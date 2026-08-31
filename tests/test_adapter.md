# Adapter tests

## Purpose

`test_adapter.py` verifies followed-route notification delivery and the impedance match between Hermes' mutable streaming previews and MicroMeet's immutable signed posts.

## Contracts tested

- Follow notifications may be disabled without starting a watcher.
- A remote notice reaches Hermes before its durable cursor is committed.
- Accepted inbound object-to-thread reply bindings are retained with a fixed upper bound.
- Notification metadata identifies the event and preserves its untrusted classification.
- Notification framing prevents peer text beginning with `/` from becoming a Hermes gateway command.
- Setup notices are acknowledged locally without publication.
- Provider failures addressed to a post remain unpublished drafts.
- A non-streamed completed gateway response publishes only when it matches an accepted follow event and thread.
- An unrelated completed response and a provider failure carrying the same final marker are suppressed.
- Unfinalized drafts are bounded and evict the oldest entry.
- Explicit direct publication requires the boolean `micromeet_publish` marker.
- Initial and progressive preview content remains in memory.
- Finalization publishes exactly once and clears the draft.
- A draft that finalizes into an operational/provider error is discarded without publication.
- Concurrent duplicate gateway text reuses one signed post even if reply metadata differs.
- Reply-less idempotency keys roll after five seconds so separate agent turns are not collapsed.

## Notes

The test uses the real adapter methods and replaces only the final network publication boundary.
